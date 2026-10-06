"""Amorce (seed) du jeu de démonstration RFM SRB Vatovavy.

Remplit les collections métier `beneficiaires`, `budgets_rfm`,
`executions` et `remboursements` avec un jeu déterministe (graine fixe)
qui alimente le tableau de bord sans aucun chiffre écrit en dur côté
frontend. Les montants sont stockés en Decimal128 et les dates en UTC,
conformément à `docs/modele-donnees.md`.

Le jeu recouvre les exercices 2025 et 2026 ; chaque exécution budgétaire
décline les quatre phases : engagement, liquidation, ordonnancement,
paiement.

Lancement (depuis `backend/`) :
    python scripts/seed.py

Attention : ressème en effaçant d'abord les quatre collections métier.
"""

from __future__ import annotations

import argparse
import asyncio
import random
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bson import Decimal128, ObjectId

from app.database import connecter_database, fermer_database, obtenir_database
from app.services.dashboard_service import (
    COLLECTION_BENEFICIAIRES,
    COLLECTION_BUDGETS,
    COLLECTION_EXECUTIONS,
    COLLECTION_REMBOURSEMENTS,
    NATURE_LFI,
    NATURE_LFR,
    PHASES_EXECUTION,
    STATUT_PAYE,
    STATUT_REFUSE,
    STATUTS_ACCEPTES,
)

GRAINE = 2025
EXERCICES = (2026, 2025)

NOMS = [
    "RAKOTO", "RABE", "RAZAFY", "RANDRIA", "ANDRIANJAKA", "RASOAMANANA",
    "RAVELOJAONA", "RATSIMBAZAFY", "RAKOTONDRABE", "RANAIVO",
    "RASAMIMANANA", "ANDRIAMAMONJY", "ANDRIANARIVELO", "RAHERINIAINA",
    "RANDRIAMANANTSOA", "RABARY", "RAZAKARISON", "ANDRIANARISON",
    "RAJAONARISON", "RATOVOHERY", "RAZAFIMANDIMBY", "RAMAROSON",
    "RAKOTONIRINA", "RANOROSOA", "ANDRINIVO",
]
PRENOMS = [
    "Hery", "Lala", "Mamy", "Voahangy", "Noro", "Tojo", "Fara", "Lova",
    "Tiana", "Mialy", "Solofo", "Onja", "Hanta", "Nirina", "Iarivo",
    "Feno", "Vonjy", "Sarobidy", "Mialia", "Rija", "Tantely", "Vola",
    "Tsiky", "Hajalaina", "Zara", "Mamisoa",
]
DIRECTIONS = [
    "Direction Régionale de l'Éducation — Vatovavy",
    "Direction Régionale de la Santé — Vatovavy",
    "Direction Régionale de l'Agriculture — Vatovavy",
    "Préfecture de Vatovavy",
    "Trésor Public de Vatovavy",
]
COMMUNES = [
    ("Vatovavy", "Ifanadiana", "Ifanadiana"),
    ("Vatovavy", "Nosy Varika", "Nosy Varika"),
    ("Vatovavy", "Mananjary", "Mananjary"),
    ("Vatovavy", "Vatovavy", "Antanambao"),
]
CATEGORIES_ACTIF = ("fonctionnaire", "contractuel")
CATEGORIES_PENSIONNE = ("retraite",)

# Lignes budgétaires de référence : (chapitre, ligne, libellé, type, montant LFI)
LIGNES_BUDGETAIRES = [
    ("31-01", "31-01-11", "Remboursements de frais de soins — actifs", "fonctionnement", 850_000_000),
    ("31-02", "31-02-12", "Remboursements de frais de soins — pensionnés", "fonctionnement", 960_000_000),
    ("31-03", "31-03-13", "Pharmacie et consommables médicaux", "fonctionnement", 410_000_000),
    ("31-04", "31-04-14", "Hospitalisation et soins lourds", "fonctionnement", 520_000_000),
    ("31-05", "31-05-15", "Prothèses et équipements médicaux", "fonctionnement", 190_000_000),
    ("32-01", "32-01-21", "Frais de fonctionnement du service RFM", "fonctionnement", 120_000_000),
    ("33-01", "33-01-31", "Investissement — système d'information", "investissement", 90_000_000),
]

PRESTATIONS = {
    "soins": (100_000, 800_000, 0.42),
    "pharmacie": (50_000, 300_000, 0.30),
    "hospitalisation": (1_000_000, 6_000_000, 0.14),
    "prothese": (800_000, 4_500_000, 0.08),
    "autre": (80_000, 500_000, 0.06),
}

STATUTS_PONDERES = (
    ("paye", 0.62), ("valide", 0.14), ("refuse", 0.10),
    ("en_attente", 0.07), ("soumis", 0.03), ("a_completer", 0.02), ("annule", 0.02),
)


def _utc(annee: int, mois: int, jour: int) -> datetime:
    return datetime(annee, mois, jour, tzinfo=timezone.utc)


def _mois_debut(annee: int, mois: int) -> datetime:
    return _utc(annee, mois, 15)


def _document(numero: int, annee: int) -> str:
    return f"RM-{annee}-{numero:05d}"


def _generer_beneficiaires(rng: random.Random) -> list[dict]:
    beneficiaires: list[dict] = []
    total = 382
    for index in range(1, total + 1):
        nom = rng.choice(NOMS)
        prenom = rng.choice(PRENOMS)
        pensionne = rng.random() < 0.32
        if pensionne:
            categorie = rng.choice(CATEGORIES_PENSIONNE)
            situation = "pensionne"
        else:
            categorie = rng.choice(CATEGORIES_ACTIF)
            situation = "actif"

        annee_creation = rng.choices((2024, 2025, 2026), weights=(0.25, 0.45, 0.30))[0]
        mois_creation = rng.randint(1, 12)
        jour_creation = min(rng.randint(1, 28), 28)
        created_at = _utc(annee_creation, mois_creation, jour_creation)

        region, district, commune = rng.choice(COMMUNES)
        beneficiaires.append({
            "matricule": f"RFM-{annee_creation}-{index:05d}",
            "nom": nom,
            "prenom": prenom,
            "date_naissance": _utc(
                rng.randint(1955, 2000), rng.randint(1, 12), rng.randint(1, 28)
            ),
            "genre": rng.choice(("M", "F")),
            "situation": situation,
            "categorie": categorie,
            "direction": rng.choice(DIRECTIONS),
            "cin": f"{rng.randint(100000000000, 999999999999)}",
            "adresse": {
                "region": region,
                "district": district,
                "commune": commune,
            },
            "statut_dossier": rng.choices(("actif", "suspendu", "clos"), weights=(0.9, 0.06, 0.04))[0],
            "created_at": created_at,
            "updated_at": created_at,
        })
    return beneficiaires


def _generer_budgets(rng: random.Random) -> list[dict]:
    budgets: list[dict] = []
    for exercice in EXERCICES:
        for chapitre, ligne, libelle, type_budget, montant_lfi in LIGNES_BUDGETAIRES:
            budgets.append({
                "exercice": exercice,
                "chapitre": chapitre,
                "ligne_budgetaire": ligne,
                "libelle": libelle,
                "type": type_budget,
                "nature": NATURE_LFI,
                "montant_vote": Decimal128(str(montant_lfi)),  # LFI (définitif si aucun LFR)
            })
            montant_lfr = int(montant_lfi * rng.uniform(1.02, 1.07))
            budgets.append({
                "exercice": exercice,
                "chapitre": chapitre,
                "ligne_budgetaire": ligne,
                "libelle": libelle,
                "type": type_budget,
                "nature": NATURE_LFR,
                "montant_vote": Decimal128(str(montant_lfr)),
            })
    return budgets


def _budget_operant(id_lfi: str, id_lfr: str) -> str:
    # L'exécution se rattache au crédit ouvrant (LFR s'il existe, sinon LFI).
    return id_lfr


def _generer_executions(rng: random.Random, budgets: list[dict]) -> list[dict]:
    operations: list[dict] = []
    par_ligne: dict[tuple[int, str], str] = {}
    for budget in budgets:
        cle = (budget["exercice"], budget["ligne_budgetaire"])
        if budget["nature"] == NATURE_LFI:
            par_ligne.setdefault(cle, budget["_id"])
        else:
            par_ligne[cle] = budget["_id"]  # le LFR devient le crédit référant

    montant_referent: dict[str, float] = {
        budget["_id"]: float(budget["montant_vote"].to_decimal())
        for budget in budgets
        if budget["nature"] == NATURE_LFR
    }

    numero = 0
    for exercice in EXERCICES:
        for cle, budget_id in par_ligne.items():
            if cle[0] != exercice:
                continue
            mensuel = montant_referent[budget_id] / 12.0
            for mois in range(1, 13):
                saison = 1.0 + 0.06 * rng.uniform(-1, 1)
                engagement = mensuel * rng.uniform(0.82, 1.12) * saison
                liquidation = engagement * rng.uniform(0.93, 0.98)
                ordonnancement = liquidation * rng.uniform(0.95, 0.98)
                paiement = ordonnancement * rng.uniform(0.95, 0.98)
                datetime_entree = _mois_debut(exercice, mois)
                for phase in PHASES_EXECUTION:
                    numero += 1
                    montant = {
                        "engagement": engagement,
                        "liquidation": liquidation,
                        "ordonnancement": ordonnancement,
                        "paiement": paiement,
                    }[phase]
                    operations.append({
                        "budget_id": budget_id,
                        "mois": f"{exercice:04d}-{mois:02d}",
                        "phase": phase,
                        "montant": Decimal128(str(round(montant, 2))),
                        "created_at": datetime_entree,
                        "updated_at": datetime_entree,
                    })
    return operations


def _generer_remboursements(rng: random.Random, beneficiaires: list[dict]) -> list[dict]:
    dossiers: list[dict] = []
    poids_prestations = [PRESTATIONS[p][2] for p in PRESTATIONS]
    types = list(PRESTATIONS.keys())
    compteur = 0
    for exercice in EXERCICES:
        volume = 520 if exercice == 2026 else 460
        for _ in range(volume):
            compteur += 1
            beneficiaire = rng.choice(beneficiaires)
            type_prestation = rng.choices(types, weights=poids_prestations)[0]
            minimum, maximum, _ = PRESTATIONS[type_prestation]
            montant_demande = rng.randint(minimum, maximum)
            statut = rng.choices(
                [s for s, _ in STATUTS_PONDERES],
                weights=[p for _, p in STATUTS_PONDERES],
            )[0]

            mois = rng.randint(1, 12)
            jour = rng.randint(1, 28)
            date_demande = _utc(exercice, mois, jour)

            montant_accordee = None
            montant_paye = None
            date_decision = None
            motif_refus = None
            if statut in STATUTS_ACCEPTES:
                montant_accordee = int(montant_demande * rng.uniform(0.7, 1.0))
            if statut == STATUT_PAYE:
                montant_paye = montant_accordee
            if statut in STATUTS_ACCEPTES or statut == STATUT_REFUSE:
                duree = rng.randint(3, 25)
                date_decision = _utc(
                    exercice,
                    mois,
                    min(28, jour + duree) if jour + duree <= 28 else jours_dans_mois(exercice, mois),
                )
                if statut == STATUT_REFUSE:
                    motif_refus = "Justificatifs incomplets"

            dossier = {
                "numero_dossier": _document(compteur, exercice),
                "beneficiaire_id": beneficiaire["_id"],
                "type_prestation": type_prestation,
                "circuit": rng.choices(("circuit_normal", "circuit_accelere"), weights=(0.8, 0.2))[0],
                "date_demande": date_demande,
                "date_decision": date_decision,
                "montant_demande": Decimal128(str(montant_demande)),
                "montant_accordee": (
                    Decimal128(str(montant_accordee)) if montant_accordee is not None else None
                ),
                "montant_paye": (
                    Decimal128(str(montant_paye)) if montant_paye is not None else None
                ),
                "statut": statut,
                "motif_refus": motif_refus,
                "pieces": [],
                "valide_par": None,
                "created_at": date_demande,
                "updated_at": date_decision or date_demande,
            }
            dossiers.append(dossier)
    return dossiers


def jours_dans_mois(annee: int, mois: int) -> int:
    if mois == 12:
        return 31
    from datetime import date as _date, timedelta
    return (_date(annee, mois + 1, 1) - timedelta(days=1)).day


async def _assurer_indexes() -> None:
    db = obtenir_database()
    await db[COLLECTION_BENEFICIAIRES].create_index([("matricule", 1)], unique=True)
    await db[COLLECTION_BUDGETS].create_index(
        [("exercice", 1), ("chapitre", 1), ("ligne_budgetaire", 1), ("nature", 1)],
        unique=True,
    )
    await db[COLLECTION_EXECUTIONS].create_index(
        [("budget_id", 1), ("mois", 1), ("phase", 1)], unique=True
    )
    await db[COLLECTION_REMBOURSEMENTS].create_index(
        [("numero_dossier", 1)], unique=True
    )


async def semer(confirmer: bool = False) -> dict:
    if not confirmer:
        raise SystemExit(
            "Abandon : passez --confirm pour effacer et réécrire les collections métier."
        )

    db = obtenir_database()
    for collection in (
        COLLECTION_BENEFICIAIRES,
        COLLECTION_BUDGETS,
        COLLECTION_EXECUTIONS,
        COLLECTION_REMBOURSEMENTS,
    ):
        await db[collection].delete_many({})
        print(f"[seed] collection '{collection}' vidée")

    rng = random.Random(GRAINE)

    beneficiaires = _generer_beneficiaires(rng)
    await db[COLLECTION_BENEFICIAIRES].insert_many(beneficiaires)

    budgets = _generer_budgets(rng)
    await db[COLLECTION_BUDGETS].insert_many(budgets)

    executions = _generer_executions(rng, budgets)
    await db[COLLECTION_EXECUTIONS].insert_many(executions, ordered=False)

    remboursements = _generer_remboursements(rng, beneficiaires)
    await db[COLLECTION_REMBOURSEMENTS].insert_many(remboursements, ordered=False)

    await _assurer_indexes()

    resume = {
        "beneficiaires": len(beneficiaires),
        "budgets_rfm": len(budgets),
        "executions": len(executions),
        "remboursements": len(remboursements),
        "exercices": list(EXERCICES),
    }
    print(f"[seed] terminé : {resume}")
    return resume


async def _principal() -> None:
    analyseur = argparse.ArgumentParser(description="Amorce des données de démonstration RFM.")
    analyseur.add_argument(
        "--confirm",
        action="store_true",
        help="Confirme l'effacement préalable des collections métier.",
    )
    arguments = analyseur.parse_args()

    await connecter_database()
    try:
        await semer(confirmer=arguments.confirm)
    finally:
        await fermer_database()


if __name__ == "__main__":
    try:
        asyncio.run(_principal())
    except SystemExit as sortie:
        print(str(sortie) or "", file=sys.stderr)
        sys.exit(1)