"""Tests du tableau de bord : calcul des indicateurs par exercice.

Vérifie :
- la synthèse sur un jeu de données connu (population, budget par phases,
  remboursements) avec des valeurs exactes attendues ;
- les séries mensuelles et les répartitions destinées aux graphiques ;
- le comportement sur un exercice sans donnée (zéro + résumé « aucune
  donnée ») ;
- les routes du tableau de bord (synthèse, exercices) et la permission
  `dashboard:voir`.

Lancement :
    python tests/test_dashboard.py
"""

import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bson import Decimal128, ObjectId

from app.api.routes.dashboard import exercices as route_exercices
from app.api.routes.dashboard import synthese as route_synthese
from app.database import connecter_database, fermer_database, obtenir_database
from app.services.dashboard_service import (
    COLLECTION_BENEFICIAIRES,
    COLLECTION_BUDGETS,
    COLLECTION_EXECUTIONS,
    COLLECTION_REMBOURSEMENTS,
    analyser_exercices,
    calculer_synthese,
)

EXERCICE = 2026

_benef_ids: list[ObjectId] = []


def _utc(annee: int, mois: int, jour: int) -> datetime:
    return datetime(annee, mois, jour, tzinfo=timezone.utc)


def _art(valeur: int) -> Decimal128:
    return Decimal128(str(valeur))


async def _nettoyer():
    db = obtenir_database()
    for collection in (
        COLLECTION_BENEFICIAIRES,
        COLLECTION_BUDGETS,
        COLLECTION_EXECUTIONS,
        COLLECTION_REMBOURSEMENTS,
    ):
        await db[collection].delete_many({})


async def _inserer_jeu():
    db = obtenir_database()
    _benef_ids.clear()

    beneficiaires = [
        {
            "matricule": "RFM-T-001", "nom": "RAKOTO", "prenom": "Hery",
            "date_naissance": _utc(1978, 4, 12), "genre": "M",
            "situation": "actif", "categorie": "fonctionnaire",
            "direction": "Direction test", "cin": "1",
            "statut_dossier": "actif",
            "created_at": _utc(2025, 6, 15), "updated_at": _utc(2025, 6, 15),
        },
        {
            "matricule": "RFM-T-002", "nom": "RABE", "prenom": "Lala",
            "date_naissance": _utc(1981, 1, 1), "genre": "F",
            "situation": "actif", "categorie": "contractuel",
            "direction": "Direction test", "cin": "2",
            "statut_dossier": "actif",
            "created_at": _utc(2025, 3, 1), "updated_at": _utc(2025, 3, 1),
        },
        {
            "matricule": "RFM-T-003", "nom": "RAZAFY", "prenom": "Mamy",
            "date_naissance": _utc(1955, 1, 1), "genre": "M",
            "situation": "pensionne", "categorie": "retraite",
            "direction": "Direction test", "cin": "3",
            "statut_dossier": "actif",
            "created_at": _utc(2025, 11, 20), "updated_at": _utc(2025, 11, 20),
        },
        {
            "matricule": "RFM-T-004", "nom": "RANDRIA", "prenom": "Noro",
            "date_naissance": _utc(1960, 1, 1), "genre": "F",
            "situation": "pensionne", "categorie": "retraite",
            "direction": "Direction test", "cin": "4",
            "statut_dossier": "actif",
            "created_at": _utc(2026, 2, 1), "updated_at": _utc(2026, 2, 1),
        },
    ]
    resultat = await db[COLLECTION_BENEFICIAIRES].insert_many(beneficiaires)
    _benef_ids.extend(resultat.inserted_ids)

    budgets = []
    for exercice, (lfi, lfr) in {
        2026: (1_000_000_000, 1_100_000_000),
        2025: (900_000_000, 950_000_000),
    }.items():
        budgets.append({
            "exercice": exercice, "chapitre": "31-01", "ligne_budgetaire": "31-01-11",
            "libelle": "Soins actifs", "type": "fonctionnement",
            "nature": "lfi", "montant_vote": _art(lfi),
        })
        budgets.append({
            "exercice": exercice, "chapitre": "31-01", "ligne_budgetaire": "31-01-11",
            "libelle": "Soins actifs", "type": "fonctionnement",
            "nature": "lfr", "montant_vote": _art(lfr),
        })
        budgets.append({
            "exercice": exercice, "chapitre": "31-04", "ligne_budgetaire": "31-04-14",
            "libelle": "Hospitalisation", "type": "fonctionnement",
            "nature": "lfi", "montant_vote": _art(600_000_000),
        })
        budgets.append({
            "exercice": exercice, "chapitre": "31-04", "ligne_budgetaire": "31-04-14",
            "libelle": "Hospitalisation", "type": "fonctionnement",
            "nature": "lfr", "montant_vote": _art(620_000_000),
        })
    resultat_budgets = await db[COLLECTION_BUDGETS].insert_many(budgets)
    for budget, identifiant in zip(budgets, resultat_budgets.inserted_ids):
        budget["_id"] = identifiant

    # Rattachement des exécutions aux crédits ouvrants (LFR).
    ids_lfr = {
        (budget["exercice"], budget["ligne_budgetaire"]): budget["_id"]
        for budget in budgets
        if budget["nature"] == "lfr"
    }

    executions = []
    for budget, phases in {
        (2026, "31-01-11"): {
            "2026-01": (10_000_000, 9_500_000, 9_000_000, 8_500_000),
            "2026-02": (12_000_000, 11_400_000, 10_800_000, 10_200_000),
        },
        (2026, "31-04-14"): {
            "2026-01": (5_000_000, 4_750_000, 4_500_000, 4_250_000),
            "2026-02": (6_000_000, 5_700_000, 5_400_000, 5_100_000),
        },
    }.items():
        budget_id = ids_lfr[budget]
        for mois, (eng, liq, ord, pay) in phases.items():
            for phase, montant in (
                ("engagement", eng), ("liquidation", liq),
                ("ordonnancement", ord), ("paiement", pay),
            ):
                executions.append({
                    "budget_id": budget_id,
                    "mois": mois,
                    "phase": phase,
                    "montant": _art(montant),
                    "created_at": _utc(2026, int(mois[5:7]), 2),
                    "updated_at": _utc(2026, int(mois[5:7]), 2),
                })
    await db[COLLECTION_EXECUTIONS].insert_many(executions)

    A, B, C, D = _benef_ids
    remboursements = [
        {
            "numero_dossier": "RM-2026-01", "beneficiaire_id": A,
            "type_prestation": "soins", "circuit": "circuit_normal",
            "date_demande": _utc(2026, 2, 15), "date_decision": _utc(2026, 3, 2),
            "montant_demande": _art(1_000_000), "montant_accordee": _art(900_000),
            "montant_paye": _art(900_000), "statut": "paye",
            "created_at": _utc(2026, 2, 15), "updated_at": _utc(2026, 3, 2),
        },
        {
            "numero_dossier": "RM-2026-02", "beneficiaire_id": B,
            "type_prestation": "hospitalisation", "circuit": "circuit_normal",
            "date_demande": _utc(2026, 3, 10), "date_decision": _utc(2026, 3, 20),
            "montant_demande": _art(2_000_000), "montant_accordee": _art(1_800_000),
            "montant_paye": _art(1_800_000), "statut": "paye",
            "created_at": _utc(2026, 3, 10), "updated_at": _utc(2026, 3, 20),
        },
        {
            "numero_dossier": "RM-2026-03", "beneficiaire_id": C,
            "type_prestation": "pharmacie", "circuit": "circuit_normal",
            "date_demande": _utc(2026, 4, 5), "date_decision": _utc(2026, 4, 15),
            "montant_demande": _art(500_000), "montant_accordee": _art(400_000),
            "montant_paye": None, "statut": "valide",
            "created_at": _utc(2026, 4, 5), "updated_at": _utc(2026, 4, 15),
        },
        {
            "numero_dossier": "RM-2026-04", "beneficiaire_id": A,
            "type_prestation": "soins", "circuit": "circuit_normal",
            "date_demande": _utc(2026, 5, 1), "date_decision": _utc(2026, 5, 10),
            "montant_demande": _art(300_000), "montant_accordee": None,
            "montant_paye": None, "statut": "refuse", "motif_refus": "incomplet",
            "created_at": _utc(2026, 5, 1), "updated_at": _utc(2026, 5, 10),
        },
        {
            "numero_dossier": "RM-2026-05", "beneficiaire_id": D,
            "type_prestation": "prothese", "circuit": "circuit_accelere",
            "date_demande": _utc(2026, 6, 1), "date_decision": None,
            "montant_demande": _art(700_000), "montant_accordee": None,
            "montant_paye": None, "statut": "soumis",
            "created_at": _utc(2026, 6, 1), "updated_at": _utc(2026, 6, 1),
        },
        {
            "numero_dossier": "RM-2025-99", "beneficiaire_id": D,
            "type_prestation": "soins", "circuit": "circuit_normal",
            "date_demande": _utc(2025, 11, 1), "date_decision": None,
            "montant_demande": _art(200_000), "montant_accordee": None,
            "montant_paye": None, "statut": "soumis",
            "created_at": _utc(2025, 11, 1), "updated_at": _utc(2025, 11, 1),
        },
    ]
    await db[COLLECTION_REMBOURSEMENTS].insert_many(remboursements)


async def _tester_population():
    synthese = await calculer_synthese(EXERCICE)
    population = synthese["population"]
    assert population["total"] == 4, population
    assert population["actifs"] == 2, population
    assert population["pensionnes"] == 2, population
    # Bénéficiaires distincts ayant au moins une demande dans l'exercice.
    assert population["beneficiaires_rfm"] == 4, population
    situations = {item["situation"]: item["total"] for item in population["repartition_par_situation"]}
    assert situations == {"actif": 2, "pensionne": 2}, situations
    print("[OK] Population : total, actifs/pensionnés, bénéficiaires RFM")

    # Recensement à fin d'exercice : le pensionné de 2025 compte pour 2026.
    synthese_2025 = await calculer_synthese(2025)
    pop_2025 = synthese_2025["population"]
    assert pop_2025["total"] == 3, pop_2025
    assert pop_2025["actifs"] == 2 and pop_2025["pensionnes"] == 1, pop_2025
    assert pop_2025["beneficiaires_rfm"] == 1, pop_2025
    situations = {item["situation"]: item["total"] for item in pop_2025["repartition_par_situation"]}
    assert situations == {"actif": 2, "pensionne": 1}, situations
    categories = {item["categorie"]: item["total"] for item in pop_2025["repartition_par_categorie"]}
    assert categories == {"retraite": 1, "fonctionnaire": 1, "contractuel": 1}, categories
    print("[OK] Population 2025 : recensement à fin d'exercice cohérent")


async def _tester_budget():
    synthese = await calculer_synthese(EXERCICE)
    budget = synthese["budget"]
    assert budget["lfi"] == 1_600_000_000, budget["lfi"]
    assert budget["lfr"] == 1_720_000_000, budget["lfr"]
    assert budget["credits_ouverts"] == 1_720_000_000, budget
    assert budget["engage"] == 33_000_000, budget["engage"]
    assert budget["liquide"] == 31_350_000, budget["liquide"]
    assert budget["ordonnance"] == 29_700_000, budget["ordonnance"]
    assert budget["execute"] == 28_050_000, budget["execute"]
    assert budget["disponible"] == 1_720_000_000 - 33_000_000, budget["disponible"]
    assert budget["solde"] == 1_720_000_000 - 28_050_000, budget["solde"]
    assert abs(budget["taux_execution"] - 28_050_000 / 1_720_000_000) < 1e-5, budget
    assert budget["lignes_budgetaires"] == 2, budget

    serie = {item["mois"]: item for item in budget["execution_mensuelle"]}
    assert len(budget["execution_mensuelle"]) == 12, budget["execution_mensuelle"]
    assert serie["2026-01"]["montant"] == 12_750_000, serie["2026-01"]
    assert serie["2026-02"]["montant"] == 15_300_000, serie["2026-02"]
    assert serie["2026-02"]["cumul"] == 28_050_000, serie["2026-02"]
    assert serie["2026-03"]["montant"] == 0.0, serie["2026-03"]
    assert serie["2026-03"]["cumul"] == 28_050_000, serie["2026-03"]

    repartition = {item["type"]: item["montant"] for item in budget["repartition_par_type"]}
    assert repartition == {"fonctionnement": 28_050_000}, repartition
    print("[OK] Budget : LFI/LFR, phases, dérivés, série mensuelle, types")


async def _tester_remboursements():
    synthese = await calculer_synthese(EXERCICE)
    rmb = synthese["remboursements"]
    assert rmb["demandes"] == 5, rmb
    assert rmb["acceptees"] == 3, rmb
    assert rmb["rejetees"] == 1, rmb
    assert rmb["en_attente"] == 1, rmb
    assert rmb["payes"] == 2, rmb
    assert rmb["montant_demande"] == 4_500_000, rmb
    assert rmb["montant_rembourse"] == 2_700_000, rmb
    assert rmb["montant_moyen_demande"] == 900_000, rmb
    assert rmb["montant_moyen_rembourse"] == 1_350_000, rmb
    assert rmb["taux_acceptation"] == 0.75, rmb

    serie = {item["mois"]: item for item in rmb["serie_mensuelle"]}
    assert serie["2026-03"]["demandes"] == 1, serie["2026-03"]
    assert serie["2026-03"]["montant_demande"] == 2_000_000, serie["2026-03"]
    assert serie["2026-03"]["rembourses"] == 2, serie["2026-03"]
    assert serie["2026-03"]["montant_rembourse"] == 2_700_000, serie["2026-03"]
    assert serie["2026-01"]["demandes"] == 0, serie["2026-01"]

    statuts = {item["statut"]: item["total"] for item in rmb["repartition_par_statut"]}
    assert statuts == {"paye": 2, "valide": 1, "refuse": 1, "soumis": 1}, statuts
    prestations = {item["type_prestation"]: item["total"] for item in rmb["repartition_par_prestation"]}
    assert prestations == {"soins": 2, "hospitalisation": 1, "pharmacie": 1, "prothese": 1}, prestations
    print("[OK] Remboursements : volumes, statuts, montants, moyennes, séries")


async def _tester_analytique():
    synthese = await calculer_synthese(EXERCICE)
    cles = {evenement["cle"] for evenement in synthese["analytique"]}
    assert "taux_execution" in cles, cles
    assert "disponible" in cles, cles
    assert "taux_acceptation" in cles, cles
    assert "montant_moyen" in cles, cles
    assert "en_attente" in cles, cles
    assert "population" in cles, cles
    for evenement in synthese["analytique"]:
        assert evenement["niveau"] in {"positif", "avertissement", "critique", "informations"}
        assert evenement["message"], evenement
    print("[OK] Résumé analytique : événements, niveaux, messages")


async def _tester_exercice_vide():
    db = obtenir_database()
    for collection in (
        COLLECTION_BENEFICIAIRES,
        COLLECTION_BUDGETS,
        COLLECTION_EXECUTIONS,
        COLLECTION_REMBOURSEMENTS,
    ):
        await db[collection].delete_many({})

    synthese = await calculer_synthese(2030)
    assert synthese["exercice"] == 2030
    assert synthese["population"]["total"] == 0
    assert synthese["budget"]["credits_ouverts"] == 0
    assert synthese["budget"]["execute"] == 0
    assert synthese["budget"]["taux_execution"] == 0
    assert synthese["remboursements"]["demandes"] == 0
    assert synthese["remboursements"]["montant_rembourse"] == 0
    assert synthese["remboursements"]["serie_mensuelle"][0]["mois"] == "2030-01"
    assert len(synthese["budget"]["execution_mensuelle"]) == 12
    assert synthese["analytique"][0]["cle"] == "aucune_donnee"
    print("[OK] Exercice sans donnée : zéros partout + résumé « aucune donnée »")

    await _inserer_jeu()  # restaure le jeu pour les tests suivants


async def _tester_routes_permission():
    utilisateur = {"_id": ObjectId(), "role": "AGENT", "email": "agent@test.mg"}
    synthese = await route_synthese(exercice=EXERCICE, _utilisateur=utilisateur)
    assert synthese["exercice"] == EXERCICE
    assert "population" in synthese and "budget" in synthese

    exercices = await analyser_exercices()
    assert exercices[0] > exercices[-1], exercices
    reponse = await route_exercices(_utilisateur=utilisateur)
    assert reponse["exercices"] == exercices
    print("[OK] Routes : synthèse + exercices (permission dashboard:voir)")


async def executer_tests():
    await connecter_database()
    try:
        await _nettoyer()
        await _inserer_jeu()
        await _tester_population()
        await _tester_budget()
        await _tester_remboursements()
        await _tester_analytique()
        await _tester_exercice_vide()
        await _tester_routes_permission()
        await _nettoyer()
    finally:
        await fermer_database()


if __name__ == "__main__":
    try:
        asyncio.run(executer_tests())
    except AssertionError as erreur:
        print(f"[ÉCHEC] {erreur}")
        sys.exit(1)
    print("TEST_DASHBOARD : OK")