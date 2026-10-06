"""Tests du module Statistiques (Pandas/NumPy) : formules côté backend.

Le jeu est inséré sur un exercice dédié (2201) avec des bénéficiaires
dédiés (situations actif / pensionné) ; le nettoyage est ciblé, aucun
impact sur la démo.

Vérifie :
- les statistiques descriptives (moyenne, médiane, variance d'échantillon,
  écart-type, quartiles, min/max, somme) ;
- la distribution (histogramme) et les percentiles ;
- les corrélations (matrice de Pearson et paires pertinentes) ;
- la comparaison actifs / pensionnés ;
- la route /analyses/statistiques et la permission `analyses:voir`.

Lancement :
    python tests/test_stats.py
"""

import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bson import Decimal128, ObjectId

from app.api.routes.analyses import statistiques as route_statistiques
from app.database import connecter_database, fermer_database, obtenir_database
from app.services.analyse_service import statistiques_data_science
from app.services.remboursement_service import (
    COLLECTION_BENEFICIAIRES,
    COLLECTION_REMBOURSEMENTS,
    _entete,
)

EXERCICE = 2201


def _utc(annee: int, mois: int, jour: int) -> datetime:
    return datetime(annee, mois, jour, tzinfo=timezone.utc)


def _art(valeur: int) -> Decimal128:
    return Decimal128(str(valeur))


def _proche(valeur: float, attendu: float, tol: float = 0.01) -> bool:
    return abs(valeur - attendu) <= tol


async def _nettoyer_jeu():
    db = obtenir_database()
    debut, fin = _entete(EXERCICE)
    await db[COLLECTION_REMBOURSEMENTS].delete_many({
        "date_demande": {"$gte": debut, "$lt": fin},
    })
    await db[COLLECTION_BENEFICIAIRES].delete_many({
        "matricule": {"$regex": r"^RFM-S-"},
    })


async def _inserer_jeu():
    db = obtenir_database()
    await _nettoyer_jeu()

    actifs = {
        "matricule": "RFM-S-001", "nom": "DATA", "prenom": "Actif",
        "date_naissance": _utc(1990, 1, 1), "genre": "M",
        "situation": "actif", "categorie": "technique",
        "direction": "Direction test", "cin": "1",
        "statut_dossier": "actif",
        "created_at": _utc(EXERCICE, 1, 1), "updated_at": _utc(EXERCICE, 1, 1),
    }
    pensionne = {
        "matricule": "RFM-S-002", "nom": "DATA", "prenom": "Pensionne",
        "date_naissance": _utc(1960, 1, 1), "genre": "F",
        "situation": "pensionne", "categorie": "retraite",
        "direction": "Direction test", "cin": "2",
        "statut_dossier": "actif",
        "created_at": _utc(EXERCICE, 1, 1), "updated_at": _utc(EXERCICE, 1, 1),
    }
    ids = await db[COLLECTION_BENEFICIAIRES].insert_many([actifs, pensionne])
    benef_actif, benef_pensionne = ids.inserted_ids

    dossiers = [
        # (beneficiaire, date_demande, date_decision, demande, accordée, payée, statut)
        # Délais prévus : 30, 20, 10, 5, 2 jours.
        (benef_actif, (1, 10), (2, 9), 100, 80, 80, "paye"),
        (benef_actif, (2, 10), (3, 2), 200, 160, 160, "paye"),
        (benef_actif, (3, 10), (3, 20), 300, 240, 240, "paye"),
        (benef_pensionne, (4, 10), (4, 15), 400, 320, 320, "paye"),
        (benef_pensionne, (5, 10), (5, 12), 500, None, None, "refuse"),
    ]
    remboursements = []
    for (beneficiaire_id, (mois, jour), (mois_dec, jour_dec),
         montant_demande, montant_accordee, montant_paye, statut) in dossiers:
        remboursements.append({
            "numero_dossier": f"ST-2201-{len(remboursements) + 1:02d}",
            "beneficiaire_id": beneficiaire_id,
            "type_prestation": "soins",
            "circuit": "circuit_normal",
            "date_demande": _utc(EXERCICE, mois, jour),
            "date_decision": _utc(EXERCICE, mois_dec, jour_dec),
            "montant_demande": _art(montant_demande),
            "montant_accordee": _art(montant_accordee) if montant_accordee else None,
            "montant_paye": _art(montant_paye) if montant_paye else None,
            "statut": statut,
            "motif_refus": None,
            "created_at": _utc(EXERCICE, 1, 1),
            "updated_at": _utc(EXERCICE, 1, 1),
        })
    await db[COLLECTION_REMBOURSEMENTS].insert_many(remboursements)


async def _tester_descriptives():
    resultat = await statistiques_data_science(EXERCICE)
    assert resultat["exercice"] == EXERCICE
    assert resultat["methode"].startswith("Pandas")
    assert resultat["nombre_documents"] == 5

    demande = resultat["descriptives"]["montant_demande"]
    assert demande["nombre"] == 5
    assert demande["moyenne"] == 300
    assert demande["mediane"] == 300
    assert demande["variance"] == 25_000
    assert _proche(demande["ecart_type"], 25_000 ** 0.5)
    assert demande["quartiles"]["q1"] == 200
    assert demande["quartiles"]["mediane"] == 300
    assert demande["quartiles"]["q3"] == 400
    assert demande["minimum"] == 100
    assert demande["maximum"] == 500
    assert demande["somme"] == 1_500

    paye = resultat["descriptives"]["montant_paye"]
    assert paye["nombre"] == 4
    assert paye["moyenne"] == 200
    assert paye["mediane"] == 200
    assert _proche(paye["variance"], 10_666.67)
    assert _proche(paye["ecart_type"], 10_666.67 ** 0.5)

    delai = resultat["descriptives"]["delai_jours"]
    assert delai["nombre"] == 5
    assert _proche(delai["moyenne"], 13.4)
    assert delai["mediane"] == 10
    assert delai["minimum"] == 2 and delai["maximum"] == 30
    print("[OK] Descriptives : moyenne, médiane, variance, écart-type, quartiles, min/max")


async def _tester_distors_et_percentiles():
    resultat = await statistiques_data_science(EXERCICE)

    distribution = resultat["distributions"]["montant_demande"]
    assert len(distribution) == 5, distribution
    assert sum(classe["effectif"] for classe in distribution) == 5
    assert all(classe["intervalle"] for classe in distribution)

    percentiles = resultat["percentiles"]["montant_demande"]
    assert percentiles["50"] == 300
    assert percentiles["25"] == 200
    assert percentiles["75"] == 400
    print("[OK] Distributions (histogramme) et percentiles")


async def _tester_correlations():
    resultat = await statistiques_data_science(EXERCICE)
    correlations = resultat["correlations"]
    matrice = correlations["matrice"]

    assert matrice["montant_demande"]["montant_paye"] == 1.0
    assert matrice["montant_demande"]["montant_accordee"] == 1.0
    assert matrice["montant_accordee"]["montant_paye"] == 1.0

    delai = matrice["montant_demande"]["delai_jours"]
    assert delai is not None and -1 < delai < 0

    pertinentes = correlations["pertinentes"]
    assert len(pertinentes) >= 3
    assert pertinentes[0]["a"] == "montant_demande"
    assert pertinentes[0]["intensite"] == "forte"
    assert pertinentes == sorted(pertinentes, key=lambda p: abs(p["correlation"]), reverse=True)
    print("[OK] Corrélations : matrice de Pearson et paires pertinentes")


async def _tester_actifs_pensionnes():
    resultat = await statistiques_data_science(EXERCICE)
    bloc = resultat["actifs_pensionnes"]

    actifs = bloc["actifs"]
    assert actifs["dossiers"] == 3
    assert actifs["montant_demande"] == 600
    assert actifs["moyenne"] == 200
    assert actifs["montant_paye"] == 480
    assert actifs["moyenne_paye"] == 160
    assert actifs["taux_acceptation"] == 1.0

    pensionnes = bloc["pensionnes"]
    assert pensionnes["dossiers"] == 2
    assert pensionnes["montant_demande"] == 900
    assert pensionnes["moyenne"] == 450
    assert pensionnes["montant_paye"] == 320
    assert pensionnes["moyenne_paye"] == 320
    assert pensionnes["taux_acceptation"] == 0.5

    par_cle = {item["cle"]: item for item in bloc["comparaison"]}
    assert par_cle["dossiers"]["actifs"] == 3
    assert par_cle["dossiers"]["pensionnes"] == 2
    assert par_cle["dossiers"]["ecart"] == 1
    assert par_cle["dossiers"]["ratio"] == 1.5
    assert par_cle["montant_demande"]["ecart"] == -300
    assert _proche(par_cle["montant_demande"]["ratio"], 600 / 900)
    assert par_cle["taux_acceptation"]["ratio"] == 2.0

    population = bloc["effectifs_population"]
    assert "actif" in population and "pensionne" in population
    assert population["actif"] >= 2 and population["pensionne"] >= 1
    print("[OK] Comparaison actifs / pensionnés")


async def _tester_route_permission():
    utilisateur = {"_id": ObjectId(), "role": "AGENT", "email": "agent@test.mg"}
    reponse = await route_statistiques(exercice=EXERCICE, _utilisateur=utilisateur)
    assert reponse["exercice"] == EXERCICE
    assert reponse["nombre_documents"] == 5
    assert "correlations" in reponse and "actifs_pensionnes" in reponse
    print("[OK] Route /analyses/statistiques (permission analyses:voir)")


async def executer_tests():
    await connecter_database()
    try:
        await _inserer_jeu()
        await _tester_descriptives()
        await _tester_distors_et_percentiles()
        await _tester_correlations()
        await _tester_actifs_pensionnes()
        await _tester_route_permission()
        await _nettoyer_jeu()
    finally:
        await _nettoyer_jeu()
        await fermer_database()


if __name__ == "__main__":
    try:
        asyncio.run(executer_tests())
    except AssertionError as erreur:
        print(f"[ÉCHEC] {erreur}")