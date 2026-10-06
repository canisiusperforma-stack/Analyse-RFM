"""Tests de l'analyse budgétaire : formules calculées côté backend.

Le jeu de test est inséré sur des exercices dédiés (2099/2098) pour ne
pas toucher aux données de démonstration ; le nettoyage est ciblé sur
les seuls documents de test.

Vérifie :
- LFI / LFR / variation, crédits ouverts = LFR sinon LFI ;
- exécution par phase (engagement, liquidation, ordonnancement, paiement) ;
- disponible = max(0, crédits - engagements), solde = crédits - paiements ;
- taux d'exécution = paiements / crédits ouverts ;
- détails par ligne budgétaire, série mensuelle, répartition par type ;
- comparaison avec l'exercice précédent ;
- les routes (synthèse, exercices) et la permission `budget:voir`.

Lancement :
    python tests/test_budget.py
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bson import Decimal128, ObjectId

from app.api.routes.budgets import exercices as route_exercices
from app.api.routes.budgets import synthese as route_synthese
from app.database import connecter_database, fermer_database, obtenir_database
from app.services.budget_service import (
    COLLECTION_BUDGETS,
    COLLECTION_EXECUTIONS,
    calculer_synthese,
    exercices_budgetaires,
)

EXERCICE = 2099
PRECEDENT = 2098

_SUPPRIMES: list[ObjectId] = []


def _art(valeur: int) -> Decimal128:
    return Decimal128(str(valeur))


async def _nettoyer_jeu():
    db = obtenir_database()
    await db[COLLECTION_BUDGETS].delete_many(
        {"exercice": {"$in": [EXERCICE, PRECEDENT]}}
    )
    if _SUPPRIMES:
        await db[COLLECTION_EXECUTIONS].delete_many(
            {"budget_id": {"$in": _SUPPRIMES}}
        )
        _SUPPRIMES.clear()


async def _inserer_jeu():
    db = obtenir_database()
    await _nettoyer_jeu()

    documents = [
        # ligne 31-01-11 : LFI + LFR
        {
            "exercice": EXERCICE, "chapitre": "31-01", "ligne_budgetaire": "31-01-11",
            "libelle": "Soins actifs", "type": "fonctionnement",
            "nature": "lfi", "montant_vote": _art(1_000_000_000),
        },
        {
            "exercice": EXERCICE, "chapitre": "31-01", "ligne_budgetaire": "31-01-11",
            "libelle": "Soins actifs", "type": "fonctionnement",
            "nature": "lfr", "montant_vote": _art(1_100_000_000),
        },
        # ligne 31-04-14 : LFI seule (crédit = LFI)
        {
            "exercice": EXERCICE, "chapitre": "31-04", "ligne_budgetaire": "31-04-14",
            "libelle": "Hospitalisation", "type": "fonctionnement",
            "nature": "lfi", "montant_vote": _art(600_000_000),
        },
        # ligne 33-01-31 : investissement, LFI + LFR
        {
            "exercice": EXERCICE, "chapitre": "33-01", "ligne_budgetaire": "33-01-31",
            "libelle": "Système d'information", "type": "investissement",
            "nature": "lfi", "montant_vote": _art(90_000_000),
        },
        {
            "exercice": EXERCICE, "chapitre": "33-01", "ligne_budgetaire": "33-01-31",
            "libelle": "Système d'information", "type": "investissement",
            "nature": "lfr", "montant_vote": _art(100_000_000),
        },
        # exercice précédent : LFI seule sur une ligne
        {
            "exercice": PRECEDENT, "chapitre": "31-01", "ligne_budgetaire": "31-01-11",
            "libelle": "Soins actifs", "type": "fonctionnement",
            "nature": "lfi", "montant_vote": _art(900_000_000),
        },
    ]
    resultats = await db[COLLECTION_BUDGETS].insert_many(documents)
    for document, _id in zip(documents, resultats.inserted_ids):
        document["_id"] = _id
    _SUPPRIMES.extend(resultats.inserted_ids)

    # Crédit ouvrant par (exercice, ligne) : le LFR s'il existe, sinon le LFI.
    referents: dict[tuple[int, str], ObjectId] = {}
    for document in documents:
        cle = (document["exercice"], document["ligne_budgetaire"])
        if referents.get(cle) is None or document["nature"] == "lfr":
            referents[cle] = document["_id"]

    mois = {
        (EXERCICE, "31-01-11"): {
            "2099-01": (10_000_000, 9_500_000, 9_000_000, 8_500_000),
            "2099-02": (12_000_000, 11_400_000, 10_800_000, 10_200_000),
        },
        (EXERCICE, "31-04-14"): {
            "2099-01": (5_000_000, 4_750_000, 4_500_000, 4_250_000),
        },
        (EXERCICE, "33-01-31"): {
            "2099-01": (3_000_000, 2_700_000, 2_400_000, 2_100_000),
        },
        (PRECEDENT, "31-01-11"): {
            "2098-01": (8_000_000, 7_000_000, 6_000_000, 5_000_000),
        },
    }

    executions = []
    for (exercice, ligne), par_mois in mois.items():
        budget_id = referents[(exercice, ligne)]
        for cle_mois, (eng, liq, ord, pay) in par_mois.items():
            for phase, montant in (
                ("engagement", eng), ("liquidation", liq),
                ("ordonnancement", ord), ("paiement", pay),
            ):
                executions.append({
                    "budget_id": budget_id,
                    "mois": cle_mois,
                    "phase": phase,
                    "montant": _art(montant),
                })
    await db[COLLECTION_EXECUTIONS].insert_many(executions)


async def _tester_totaux():
    synthese = await calculer_synthese(EXERCICE)
    total = synthese["total"]
    assert total["lfi"] == 1_690_000_000, total
    assert total["lfr"] == 1_200_000_000, total
    assert total["variation"] == 1_200_000_000 - 1_690_000_000, total
    assert abs(total["variation_pct"] - (-490_000_000 / 1_690_000_000)) < 1e-6, total
    assert total["credits"] == 1_800_000_000, total  # LFR sinon LFI, par ligne
    assert total["engagement"] == 30_000_000, total
    assert total["liquidation"] == 28_350_000, total
    assert total["ordonnancement"] == 26_700_000, total
    assert total["execute"] == 25_050_000, total
    assert total["disponible"] == 1_800_000_000 - 30_000_000, total
    assert total["solde"] == 1_800_000_000 - 25_050_000, total
    assert abs(
        total["taux_execution"] - 25_050_000 / 1_800_000_000
    ) < 1e-6, total
    assert total["lignes_budgetaires"] == 3, total
    print("[OK] Totaux : LFI/LFR/variation, phases, disponible, solde, taux")


async def _tester_lignes():
    synthese = await calculer_synthese(EXERCICE)
    lignes = {ligne["ligne_budgetaire"]: ligne for ligne in synthese["lignes"]}
    assert len(lignes) == 3, lignes

    soins = lignes["31-01-11"]
    assert soins["lfi"] == 1_000_000_000 and soins["lfr"] == 1_100_000_000, soins
    assert soins["variation"] == 100_000_000, soins
    assert abs(soins["variation_pct"] - 0.1) < 1e-6, soins
    assert soins["credits"] == 1_100_000_000, soins
    assert soins["engagement"] == 22_000_000, soins
    assert soins["execute"] == 18_700_000, soins
    assert soins["disponible"] == 1_100_000_000 - 22_000_000, soins
    assert soins["solde"] == 1_100_000_000 - 18_700_000, soins
    assert abs(soins["taux_execution"] - 18_700_000 / 1_100_000_000) < 1e-6, soins

    hospitalisation = lignes["31-04-14"]  # pas de LFR : crédit = LFI
    assert hospitalisation["lfr"] == 0.0, hospitalisation
    assert hospitalisation["credits"] == 600_000_000, hospitalisation
    assert hospitalisation["variation"] == 0 - 600_000_000, hospitalisation

    investissement = lignes["33-01-31"]
    assert investissement["type"] == "investissement", investissement
    assert investissement["variation"] == 10_000_000, investissement
    assert abs(investissement["variation_pct"] - 10_000_000 / 90_000_000) < 1e-6, investissement
    print("[OK] Détail par ligne : LFI/LFR, variation, crédits, phases, taux")


async def _tester_serie():
    synthese = await calculer_synthese(EXERCICE)
    serie = {item["mois"]: item for item in synthese["serie_mensuelle"]}
    assert len(synthese["serie_mensuelle"]) == 12, synthese["serie_mensuelle"]

    janvier = serie["2099-01"]
    assert janvier["engagement"] == 18_000_000, janvier
    assert janvier["liquidation"] == 16_950_000, janvier
    assert janvier["ordonnancement"] == 15_900_000, janvier
    assert janvier["paiement"] == 14_850_000, janvier
    assert janvier["cumul"] == 14_850_000, janvier

    fevrier = serie["2099-02"]
    assert fevrier["paiement"] == 10_200_000, fevrier
    assert fevrier["cumul"] == 25_050_000, fevrier

    mars = serie["2099-03"]
    assert mars["paiement"] == 0.0, mars
    assert mars["cumul"] == 25_050_000, mars
    assert serie["2099-12"]["cumul"] == 25_050_000, serie["2099-12"]
    print("[OK] Série mensuelle : phases et cumul des paiements")


async def _tester_repartition():
    synthese = await calculer_synthese(EXERCICE)
    par_type = {item["type"]: item for item in synthese["repartition_par_type"]}
    assert len(par_type) == 2, par_type
    fonctionnement = par_type["fonctionnement"]
    assert fonctionnement["credits"] == 1_700_000_000, fonctionnement
    assert fonctionnement["execute"] == 22_950_000, fonctionnement
    assert fonctionnement["lignes"] == 2, fonctionnement
    investissement = par_type["investissement"]
    assert investissement["credits"] == 100_000_000, investissement
    assert investissement["execute"] == 2_100_000, investissement
    # tri décroissant par exécution
    assert synthese["repartition_par_type"][0]["type"] == "fonctionnement"
    print("[OK] Répartition par type : crédits, exécution, taux")


async def _tester_comparaison():
    synthese = await calculer_synthese(EXERCICE)
    comparaison = synthese["comparaison"]
    assert comparaison is not None, synthese
    assert comparaison["exercice_precedent"] == PRECEDENT, comparaison
    assert comparaison["credits_precedent"] == 900_000_000, comparaison
    assert comparaison["execute_precedent"] == 5_000_000, comparaison
    assert comparaison["ecart_credits"] == 1_800_000_000 - 900_000_000, comparaison
    assert comparaison["ecart_execute"] == 25_050_000 - 5_000_000, comparaison
    assert compproche(comparaison["ecart_disponible"], 1_770_000_000 - 892_000_000), comparaison
    assert compproche(comparaison["ecart_solde"], 1_774_950_000 - 895_000_000), comparaison
    assert abs(compara_variation_pct(comparaison) - 1.0) < 1e-6, comparaison
    print("[OK] Comparaison avec l'exercice précédent")

    sans_precedent = await calculer_synthese(PRECEDENT)
    assert sans_precedent["comparaison"] is None, sans_precedent


def compproche(valeur: float, attendu: float, tol: float = 0.001):
    return abs(valeur - attendu) <= tol


def compara_variation_pct(comparaison: dict):
    return comparaison["variation_pct_credits"]


async def _tester_routes_permission():
    utilisateur = {"_id": ObjectId(), "role": "AGENT", "email": "agent@test.mg"}
    synthese = await route_synthese(exercice=EXERCICE, _utilisateur=utilisateur)
    assert synthese["exercice"] == EXERCICE
    assert synthese["total"]["credits"] == 1_800_000_000
    assert "lignes" in synthese and "comparaison" in synthese

    disponibles = await exercices_budgetaires()
    assert EXERCICE in disponibles and PRECEDENT in disponibles
    assert disponibles == sorted(disponibles, reverse=True), disponibles
    reponse = await route_exercices(_utilisateur=utilisateur)
    assert reponse["exercices"] == disponibles, reponse
    print("[OK] Routes : synthèse + exercices (permission budget:voir)")


async def executer_tests():
    await connecter_database()
    try:
        await _inserer_jeu()
        await _tester_totaux()
        await _tester_lignes()
        await _tester_serie()
        await _tester_repartition()
        await _tester_comparaison()
        await _tester_routes_permission()
        await _nettoyer_jeu()
    finally:
        await _nettoyer_jeu()
        await fermer_database()


if __name__ == "__main__":
    try:
        asyncio.run(executer_tests())
    except AssertionError as erreur:
        print(f"[ÉCHEC] {erreur}")
        sys.exit(1)
    print("TEST_BUDGET : OK")