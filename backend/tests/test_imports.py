"""Tests du pipeline d'importation de données RFM (CSV + XLSX).

Vérifie :
- upload/lecture CSV et Excel ;
- détection des colonnes et des types ;
- validation des types, gestion des valeurs manquantes ;
- détection des doublons ;
- normalisation des montants et des dates ;
- rapport d'importation (compteurs, rejets et motifs) ;
- traçabilité (qui, quand, quel fichier) ;
- conservation des données brutes (fichier original + lignes brutes) ;
- non-création de collections métier.

Lancement :
    python tests/test_imports.py
"""

import asyncio
import sys
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bson import Decimal128, ObjectId
from openpyxl import Workbook

from app.database import connecter_database, fermer_database, obtenir_database
from app.imports import importer_fichier, lire_fichier_original
from app.imports.colonnes import lire_fichier
from app.imports.erreurs import ErreurImportation
from app.imports.models import OptionsImportation
from app.imports.pipeline import TAILLE_MAX_OCTETS
from app.imports.stockage import (
    COLLECTION_BRUTES,
    COLLECTION_IMPORTATIONS,
    COLLECTION_NETTOYEES,
    COLLECTION_REJETS,
    _bucket,
)

THEME_CSV = (
    "Matricule;Nom;Prénom;Date de naissance;Situation;Montant cotisation;Exercice\n"
    "RFM-2025-001;RAKOTO;Hery;12/04/1978;actif;1 500 000;2025\n"
    "RFM-2025-002;RABE;Lala;05/11/1980;pensionne;2 200 000,00;2025\n"
    "RFM-2025-003;RAZAFY;Mamy;30/01/1991;pensionne;1 750 000 Ar;2025\n"
    "RFM-2025-004;RANDRIA;Noro;15-03-1985;actif;abc;2025\n"
    "RFM-2025-002;RABE;Lala;05/11/1980;pensionne;2 200 000,00;2025\n"
    "RFM-2025-005;ANDRIANAZY;Tojo;;;900 000;2025\n"
)

COLLECTIONS_METIER = {
    "beneficiaires", "remboursements", "budgets_rfm", "executions",
    "previsions", "simulations", "anomalies", "documents", "rapports",
}

_identifiants_crees: list[ObjectId] = []

_collections_metier_initiales: set[str] = set()


def _contenu_xlsx() -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "RFM"
    ws.append(["Matricule", "Nom", "DateNaissance", "Montant", "Exercice"])
    ws.append(["RFM-2026-001", "RAVELO", "02/03/1975", 1_250_000, 2026])
    ws.append(["RFM-2026-002", "RAVONISOA", "18/09/1988", 940_500.5, 2026])
    buffer = BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


async def _verifier_colonnes():
    headers, grille, meta = lire_fichier(
        THEME_CSV.encode("utf-8-sig"),
        "test_rfm_2025.csv",
    )
    assert meta["format"] == "csv"
    assert meta["delimiteur"] == ";"
    assert meta["encodage"] in ("utf-8", "utf-8-sig")
    assert headers[0] == "Matricule"
    assert len(grille) == 6
    print("[OK] Lecture CSV + détection séparateur/encodage")


async def _nettoyer(identifiant: ObjectId):
    db = obtenir_database()
    await db[COLLECTION_REJETS].delete_many({"importation_id": identifiant})
    await db[COLLECTION_BRUTES].delete_many({"importation_id": identifiant})
    await db[COLLECTION_NETTOYEES].delete_many({"importation_id": identifiant})
    meta = await db[COLLECTION_IMPORTATIONS].find_one({"_id": identifiant})
    if meta and meta.get("fichier_id"):
        try:
            await _bucket().delete(meta["fichier_id"])
        except Exception:
            pass
    await db[COLLECTION_IMPORTATIONS].delete_one({"_id": identifiant})


async def _tester_pipeline_csv():
    utilisateur = ObjectId()
    donnees = THEME_CSV.encode("utf-8-sig")
    resultat = await importer_fichier(
        donnees,
        "test_rfm_2025.csv",
        importe_par=utilisateur,
    )
    _identifiants_crees.append(ObjectId(resultat["id"]))
    _identifiants_crees.append(utilisateur)

    assert resultat["statut"] == "termine", resultat.get("erreur")
    rapport = resultat["rapport"]
    assert rapport["nb_lignes_total"] == 6, rapport
    assert rapport["nb_lignes_importees"] == 4, rapport
    assert rapport["nb_lignes_rejetees"] == 2, rapport
    assert rapport["nb_doublons"] == 1, rapport
    assert rapport["nb_colonnes"] == 7, rapport
    assert rapport["format"] == "csv"
    assert rapport["delimiteur"] == ";"
    print("[OK] Compteurs du rapport : 6 total / 4 nettes / 2 rejetées / 1 doublon")

    motifs = [(r["ligne"], r["type_erreur"]) for r in rapport["rejets"]]
    assert (4, "type") in motifs, motifs
    assert (5, "doublon") in motifs, motifs
    motifs_doublon = [m for m in resultat["rapport"]["rejets"] if m["type_erreur"] == "doublon"]
    assert "ligne 1" in motifs_doublon[0]["raison"] or "ligne 2" in motifs_doublon[0]["raison"], motifs_doublon
    print("[OK] Motifs de rejet : ligne 4 (type), ligne 5 (doublon)")

    for col in rapport["colonnes"]:
        if col["nom_normalise"] == "montant_cotisation":
            assert col["nb_invalides"] == 1, col
        if col["nom_normalise"] == "date_de_naissance":
            assert col["nb_vides"] == 1, col
    print("[OK] Statistiques par colonne (invalides/vides)")

    assert resultat["importe_par"] == str(utilisateur), resultat
    assert resultat["importe_le"] is not None
    assert resultat["nom_fichier"] == "test_rfm_2025.csv"
    print("[OK] Traçabilité : qui (utilisateur), quand, quel fichier")

    db = obtenir_database()
    brut = await db[COLLECTION_BRUTES].find_one(
        {"importation_id": ObjectId(resultat["id"]), "ligne": 1}
    )
    assert brut["valeurs"]["Montant cotisation"] == "1 500 000", brut
    print("[OK] Données brutes conservées sans modification")

    nette = await db[COLLECTION_NETTOYEES].find_one(
        {"importation_id": ObjectId(resultat["id"]), "ligne": 1}
    )
    assert nette["valeurs"]["montant_cotisation"] == Decimal128("1500000"), nette
    assert nette["valeurs"]["date_de_naissance"] == datetime(
        1978, 4, 12, tzinfo=timezone.utc
    ), nette
    assert nette["valeurs"]["exercice"] == 2025, nette

    nette6 = await db[COLLECTION_NETTOYEES].find_one(
        {"importation_id": ObjectId(resultat["id"]), "ligne": 6}
    )
    assert "date_de_naissance" in nette6["manquantes"], nette6
    assert "situation" in nette6["manquantes"], nette6
    print("[OK] Normalisation montants/dates et valeurs manquantes repérées")

    fichier_id = (await db[COLLECTION_IMPORTATIONS].find_one({"_id": ObjectId(resultat["id"])}))["fichier_id"]
    retour = await lire_fichier_original(fichier_id)
    assert retour == donnees, "Le fichier original doit être restitué à l'identique"
    print("[OK] Fichier original stocké et restitué (GridFS, intact)")


async def _tester_colonnes_obligatoires():
    csv = (
        "Matricule;Nom\n"
        "RFM-A;AAA\n"
        ";BBB\n"
    ).encode("utf-8")
    resultat = await importer_fichier(
        csv,
        "test_obligatoires.csv",
        options=OptionsImportation(colonnes_obligatoires=["matricule"]),
    )
    _identifiants_crees.append(ObjectId(resultat["id"]))
    rapport = resultat["rapport"]
    assert rapport["nb_lignes_total"] == 2, rapport
    assert rapport["nb_lignes_importees"] == 1, rapport
    motifs = [(r["ligne"], r["type_erreur"]) for r in rapport["rejets"]]
    assert (2, "obligatoire") in motifs, motifs
    print("[OK] Colonne obligatoire manquante => ligne rejetée")


async def _tester_pipeline_xlsx():
    resultat = await importer_fichier(
        _contenu_xlsx(),
        "test_rfm_2026.xlsx",
    )
    _identifiants_crees.append(ObjectId(resultat["id"]))
    rapport = resultat["rapport"]
    assert rapport["format"] == "xlsx", rapport
    assert rapport["nb_lignes_total"] == 2, rapport
    assert rapport["nb_lignes_importees"] == 2, rapport
    assert rapport["nb_lignes_rejetees"] == 0, rapport
    print("[OK] Importation Excel (openpyxl) réussie")


async def _tester_erreurs():
    try:
        await importer_fichier(b"", "vide.csv")
        raise AssertionError("fichier vide doit être rejeté")
    except ErreurImportation:
        pass

    try:
        await importer_fichier(b"Mauvais", "donnees.parquet")
        raise AssertionError("extension non autorisée doit être rejetée")
    except ErreurImportation:
        pass

    gros = b"x" * (TAILLE_MAX_OCTETS + 1)
    try:
        await importer_fichier(gros, "gros.csv")
        raise AssertionError("fichier trop volumineux doit être rejeté")
    except ErreurImportation:
        pass
    print("[OK] Garde-fous : fichier vide, format non supporté, taille max")


async def _verifier_aucune_collection_metier():
    db = obtenir_database()
    collections = await db.list_collection_names()
    croisement = COLLECTIONS_METIER & set(collections)
    nouvelles = croisement - _collections_metier_initiales
    assert not nouvelles, (
        f"L'import a créé des collections métier : {sorted(nouvelles)}"
    )
    attendues = {
        "importations", "importations_brutes",
        "importations_nettoyees", "importations_rejets",
    }
    assert attendues.issubset(set(collections)), collections
    print("[OK] Aucune collection métier créée à l'import ; seules les collections d'import existent")


async def _nettoyer_tout():
    for identifiant in _identifiants_crees:
        await _nettoyer(identifiant)
    print("[OK] Nettoyage des données de test")


async def executer_tests():
    global _collections_metier_initiales
    await connecter_database()
    try:
        db = obtenir_database()
        _collections_metier_initiales = COLLECTIONS_METIER & set(
            await db.list_collection_names()
        )
        await _verifier_colonnes()
        await _tester_pipeline_csv()
        await _tester_colonnes_obligatoires()
        await _tester_pipeline_xlsx()
        await _tester_erreurs()
        await _verifier_aucune_collection_metier()
        await _nettoyer_tout()
    finally:
        await fermer_database()


if __name__ == "__main__":
    try:
        asyncio.run(executer_tests())
    except AssertionError as erreur:
        print(f"[ÉCHEC] {erreur}")
        sys.exit(1)
    except ErreurImportation as erreur:
        print(f"[ÉCHEC] {erreur}")
        sys.exit(1)
    print("TEST_IMPORTS : OK")