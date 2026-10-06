"""Tests de la page Bénéficiaires : population, filtres, comparaisons.

Vérifie :
- les statistiques de la population sur un jeu connu (total, actifs,
  pensionnés, bénéficiaires RFM, tranches d'âge, moyenne d'âge,
  répartitions, comparaison à l'exercice précédent) ;
- la liste filtrable et paginée (recherche, situation, catégorie, rfm,
  tri, pagination) ;
- le repli sur les importations normalisées (source `importation`)
  lorsque les collections métier sont vides ;
- les routes (statistiques, liste, exercices) et la permission
  `beneficiaires:voir`.

Lancement :
    python tests/test_beneficiaires.py
"""

import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bson import Decimal128, ObjectId

from app.api.routes.beneficiaires import (
    exercices as route_exercices,
    lister as route_lister,
    statistiques as route_statistiques,
)
from app.database import connecter_database, fermer_database, obtenir_database
from app.services.beneficiaires_service import (
    COLLECTION_IMPORTS_NETTOYEES,
    SOURCE_IMPORTATION,
    SOURCE_METIER,
    exercices_population,
    lister_beneficiaires,
    statistiques_population,
)
from app.services.dashboard_service import (
    COLLECTION_BENEFICIAIRES,
    COLLECTION_REMBOURSEMENTS,
)

EXERCICE = 2026

_ident_ids: list[ObjectId] = []


def _utc(annee: int, mois: int, jour: int) -> datetime:
    return datetime(annee, mois, jour, tzinfo=timezone.utc)


def _art(valeur: int) -> Decimal128:
    return Decimal128(str(valeur))


async def _nettoyer():
    db = obtenir_database()
    for collection in (
        COLLECTION_BENEFICIAIRES,
        COLLECTION_REMBOURSEMENTS,
        COLLECTION_IMPORTS_NETTOYEES,
    ):
        await db[collection].delete_many({})


async def _inserer_jeu_metier():
    db = obtenir_database()
    _ident_ids.clear()
    beneficiaires = [
        {
            "matricule": "RFM-T-001", "nom": "RAKOTO", "prenom": "Hery",
            "date_naissance": _utc(1978, 4, 12), "genre": "M",
            "situation": "actif", "categorie": "fonctionnaire",
            "direction": "Direction test", "cin": "1", "statut_dossier": "actif",
            "created_at": _utc(2025, 6, 15), "updated_at": _utc(2025, 6, 15),
        },
        {
            "matricule": "RFM-T-002", "nom": "RABE", "prenom": "Lala",
            "date_naissance": _utc(1981, 1, 1), "genre": "F",
            "situation": "actif", "categorie": "contractuel",
            "direction": "Direction test", "cin": "2", "statut_dossier": "actif",
            "created_at": _utc(2025, 3, 1), "updated_at": _utc(2025, 3, 1),
        },
        {
            "matricule": "RFM-T-003", "nom": "RAZAFY", "prenom": "Mamy",
            "date_naissance": _utc(1955, 1, 1), "genre": "M",
            "situation": "pensionne", "categorie": "retraite",
            "direction": "Direction test", "cin": "3", "statut_dossier": "actif",
            "created_at": _utc(2025, 11, 20), "updated_at": _utc(2025, 11, 20),
        },
        {
            "matricule": "RFM-T-004", "nom": "RANDRIA", "prenom": "Noro",
            "date_naissance": _utc(1960, 1, 1), "genre": "F",
            "situation": "pensionne", "categorie": "retraite",
            "direction": "Direction test", "cin": "4", "statut_dossier": "actif",
            "created_at": _utc(2026, 2, 1), "updated_at": _utc(2026, 2, 1),
        },
    ]
    resultat = await db[COLLECTION_BENEFICIAIRES].insert_many(beneficiaires)
    _ident_ids.extend(resultat.inserted_ids)

    A, B, C, D = _ident_ids
    remboursements = [
        {
            "numero_dossier": "RM-2026-01", "beneficiaire_id": A,
            "type_prestation": "soins", "date_demande": _utc(2026, 2, 15),
            "date_decision": _utc(2026, 3, 2),
            "montant_demande": _art(1_000_000), "montant_accordee": _art(900_000),
            "montant_paye": _art(900_000), "statut": "paye",
            "created_at": _utc(2026, 2, 15), "updated_at": _utc(2026, 3, 2),
        },
        {
            "numero_dossier": "RM-2026-02", "beneficiaire_id": B,
            "type_prestation": "soins", "date_demande": _utc(2026, 3, 10),
            "date_decision": _utc(2026, 4, 1),
            "montant_demande": _art(600_000), "montant_accordee": _art(500_000),
            "montant_paye": None, "statut": "valide",
            "created_at": _utc(2026, 3, 10), "updated_at": _utc(2026, 4, 1),
        },
        {
            "numero_dossier": "RM-2026-03", "beneficiaire_id": C,
            "type_prestation": "pharmacie", "date_demande": _utc(2026, 4, 5),
            "date_decision": _utc(2026, 4, 15),
            "montant_demande": _art(300_000), "montant_accordee": _art(250_000),
            "montant_paye": None, "statut": "valide",
            "created_at": _utc(2026, 4, 5), "updated_at": _utc(2026, 4, 15),
        },
        {
            "numero_dossier": "RM-2026-04", "beneficiaire_id": D,
            "type_prestation": "prothese", "date_demande": _utc(2026, 5, 1),
            "date_decision": _utc(2026, 5, 10),
            "montant_demande": _art(700_000), "montant_accordee": _art(650_000),
            "montant_paye": None, "statut": "valide",
            "created_at": _utc(2026, 5, 1), "updated_at": _utc(2026, 5, 10),
        },
        {
            "numero_dossier": "RM-2025-99", "beneficiaire_id": D,
            "type_prestation": "soins", "date_demande": _utc(2025, 11, 1),
            "date_decision": None,
            "montant_demande": _art(200_000), "montant_accordee": None,
            "montant_paye": None, "statut": "soumis",
            "created_at": _utc(2025, 11, 1), "updated_at": _utc(2025, 11, 1),
        },
    ]
    await db[COLLECTION_REMBOURSEMENTS].insert_many(remboursements)


async def _tester_statistiques():
    resultat = await statistiques_population(EXERCICE)
    assert resultat["source"] == SOURCE_METIER, resultat["source"]
    assert resultat["total"] == 4, resultat
    assert resultat["actifs"] == 2, resultat
    assert resultat["pensionnes"] == 2, resultat
    assert resultat["indetermines"] == 0, resultat
    assert resultat["beneficiaires_rfm"] == 4, resultat
    assert resultat["taux_dactifs"] == 0.5, resultat

    situations = {
        item["situation"]: item["total"]
        for item in resultat["repartition_par_situation"]
    }
    assert situations == {"actif": 2, "pensionne": 2}, situations
    categories = {
        item["categorie"]: item["total"]
        for item in resultat["repartition_par_categorie"]
    }
    assert categories == {"fonctionnaire": 1, "contractuel": 1, "retraite": 2}, categories
    genres = {item["genre"]: item["total"] for item in resultat["repartition_par_genre"]}
    assert genres == {"M": 2, "F": 2}, genres

    tranches = {item["tranche"]: item["total"] for item in resultat["tranches_age"]}
    assert tranches == {"moins_de_30": 0, "30_a_39": 0, "40_a_49": 2, "50_a_59": 0, "60_et_plus": 2}, tranches
    assert resultat["moyenne_age"] is not None
    assert 40 <= resultat["age_minimal"] <= 60, resultat
    assert resultat["age_maximal"] == 72, resultat
    assert "Direction test" in {
        item["direction"] for item in resultat["repartition_par_direction"]
    }
    print("[OK] Statistiques : total, actifs/pensionnés, RFM, âges, répartitions")

    comparaison = resultat["comparaison"]
    assert comparaison is not None, comparaison
    assert comparaison["exercice_precedent"] == 2025, comparaison
    assert comparaison["total"] == 4, comparaison
    assert comparaison["ecart_total"] == 1, comparaison
    assert comparaison["actifs"] == 2 and comparaison["ecart_actifs"] == 0, comparaison
    assert comparaison["pensionnes"] == 2 and comparaison["ecart_pensionnes"] == 1, comparaison
    assert comparaison["beneficiaires_rfm"] == 4 and comparaison["ecart_rfm"] == 4, comparaison
    print("[OK] Comparaison avec l'exercice précédent (2025)")

    resultat_2025 = await statistiques_population(2025)
    assert resultat_2025["total"] == 3, resultat_2025
    assert resultat_2025["actifs"] == 2 and resultat_2025["pensionnes"] == 1, resultat_2025
    assert resultat_2025["beneficiaires_rfm"] == 0, resultat_2025
    assert resultat_2025["comparaison"] is None, resultat_2025["comparaison"]
    print("[OK] Statistiques 2025 : recensement à fin d'exercice")


async def _tester_liste():
    liste = await lister_beneficiaires(exercice=EXERCICE)
    assert liste["total"] == 4 and len(liste["items"]) == 4, liste
    assert {item["situation"] for item in liste["items"]} == {"actif", "pensionne"}, liste

    recherche = await lister_beneficiaires(exercice=EXERCICE, recherche="RAZAFY")
    assert recherche["total"] == 1, recherche
    assert recherche["items"][0]["matricule"] == "RFM-T-003", recherche

    recherche_prenom = await lister_beneficiaires(exercice=EXERCICE, recherche="noro")
    assert recherche_prenom["total"] == 1, recherche_prenom
    assert recherche_prenom["items"][0]["matricule"] == "RFM-T-004", recherche_prenom

    actifs = await lister_beneficiaires(exercice=EXERCICE, situation="actif")
    assert actifs["total"] == 2, actifs

    retraites = await lister_beneficiaires(exercice=EXERCICE, categorie="retraite")
    assert retraites["total"] == 2, retraites

    rfm_oui = await lister_beneficiaires(exercice=EXERCICE, rfm="oui")
    assert rfm_oui["total"] == 4, rfm_oui
    rfm_non_2025 = await lister_beneficiaires(exercice=2025, rfm="non")
    assert rfm_non_2025["total"] == 3, rfm_non_2025

    tries = await lister_beneficiaires(exercice=EXERCICE, tri="age", ordre="desc")
    assert tries["items"][0]["matricule"] == "RFM-T-003", tries["items"]

    paginee = await lister_beneficiaires(exercice=EXERCICE, limite=2, saut=0)
    assert paginee["total"] == 4 and len(paginee["items"]) == 2, paginee
    print("[OK] Liste : recherche, filtres, RFM, tri, pagination")


async def _tester_routes_permission():
    utilisateur = {"_id": ObjectId(), "role": "AGENT", "email": "agent@test.mg"}
    reponse = await route_statistiques(exercice=EXERCICE, _utilisateur=utilisateur)
    assert reponse["exercice"] == EXERCICE, reponse
    assert reponse["total"] == 4, reponse

    liste = await route_lister(exercice=EXERCICE, _utilisateur=utilisateur)
    assert liste["total"] == 4, liste

    disponibles = await exercices_population()
    assert EXERCICE in disponibles, disponibles
    reponse_exercices = await route_exercices(_utilisateur=utilisateur)
    assert reponse_exercices["exercices"] == disponibles, reponse_exercices
    print("[OK] Routes : statistiques, liste, exercices (permission beneficiaires:voir)")


async def _tester_repli_importation():
    db = obtenir_database()
    for collection in (COLLECTION_BENEFICIAIRES, COLLECTION_REMBOURSEMENTS):
        await db[collection].delete_many({})

    importations = [
        {
            "importation_id": ObjectId(), "ligne": 1,
            "valeurs": {
                "matricule": "IMP-001", "nom": "ANDRIAM", "prenom": "Tojo",
                "date_de_naissance": _utc(1990, 5, 1),
                "situation": "actif", "exercice": 2026,
            },
        },
        {
            "importation_id": ObjectId(), "ligne": 2,
            "valeurs": {
                "matricule": "IMP-002", "nom": "RASOLO", "prenom": "Onja",
                "date_de_naissance": _utc(1970, 3, 3),
                "situation": "pensionne", "exercice": 2026,
            },
        },
        {
            "importation_id": ObjectId(), "ligne": 3,
            "valeurs": {
                "matricule": "IMP-003", "nom": "RAVELO", "prenom": "Fara",
                "date_de_naissance": _utc(1985, 8, 8),
                "situation": "actif", "exercice": 2025,
            },
        },
    ]
    await db[COLLECTION_IMPORTS_NETTOYEES].insert_many(importations)

    resultat = await statistiques_population(EXERCICE)
    assert resultat["source"] == SOURCE_IMPORTATION, resultat["source"]
    assert resultat["total"] == 2, resultat
    assert resultat["actifs"] == 1 and resultat["pensionnes"] == 1, resultat
    assert resultat["beneficiaires_rfm"] == 0, resultat

    liste = await lister_beneficiaires(exercice=EXERCICE, recherche="RAS")
    assert liste["total"] == 1 and liste["items"][0]["matricule"] == "IMP-002", liste

    disponibles = await exercices_population()
    assert disponibles == [2026, 2025], disponibles
    print("[OK] Repli importation : source, statistiques, liste, exercices")

    await db[COLLECTION_IMPORTS_NETTOYEES].delete_many({})


async def executer_tests():
    await connecter_database()
    try:
        await _nettoyer()
        await _inserer_jeu_metier()
        await _tester_statistiques()
        await _tester_liste()
        await _tester_routes_permission()
        await _tester_repli_importation()
        await _nettoyer()
    finally:
        await fermer_database()


if __name__ == "__main__":
    try:
        asyncio.run(executer_tests())
    except AssertionError as erreur:
        print(f"[ÉCHEC] {erreur}")
        sys.exit(1)
    print("TEST_BENEFICIAIRES : OK")