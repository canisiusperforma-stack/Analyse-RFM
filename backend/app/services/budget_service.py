"""Analyse budgétaire détaillée par exercice (agrégations MongoDB).

Complète `dashboard_service` avec la vue « Budget » : LFI / LFR par ligne
budgétaire, variation, crédits ouverts, exécution par phase (engagement,
liquidation, ordonnancement, paiement), disponible, solde et taux
d'exécution. Toutes les formules sont calculées ici, côté backend, à
partir des collections `budgets_rfm` et `executions` ; le frontend ne
contient aucun chiffre.

Conventions (identiques à `dashboard_service`) :
- chaque exécution est rattachée au crédit ouvrant (LFR s'il existe,
  sinon LFI) via `executions.budget_id` ;
- `crédits ouverts = LFR si voté, sinon LFI` ;
- `disponible = max(0, crédits ouverts - engagements)` ;
- `solde = crédits ouverts - paiements exécutés` (négatif = dépassement) ;
- `taux d'exécution = paiements / crédits ouverts`.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional

from bson import Decimal128

from app.database import obtenir_database

COLLECTION_BUDGETS = "budgets_rfm"
COLLECTION_EXECUTIONS = "executions"

NATURE_LFI = "lfi"
NATURE_LFR = "lfr"

PHASES_EXECUTION = ("engagement", "liquidation", "ordonnancement", "paiement")
PHASE_FINALE = "paiement"


def _montant(document: dict[str, Any], champ: str) -> float:
    """Renvoie la valeur (Decimal128 | Decimal | int | float | None) en float."""
    valeur = document.get(champ)
    if valeur is None:
        return 0.0
    if isinstance(valeur, Decimal128):
        return float(valeur.to_decimal())
    if isinstance(valeur, Decimal):
        return float(valeur)
    return float(valeur)


def _acroissir(montant: float) -> float:
    return round(montant, 2)


def _mois_de_lexercice(exercice: int) -> list[str]:
    return [f"{exercice:04d}-{mois:02d}" for mois in range(1, 13)]


async def exercices_budgetaires() -> list[int]:
    """Exercices présents dans les crédits votés (ordre décroissant)."""
    db = obtenir_database()
    cursor = db[COLLECTION_BUDGETS].aggregate([{"$group": {"_id": "$exercice"}}])
    exercices: set[int] = set()
    async for doc in cursor:
        exercices.add(int(doc["_id"]))
    return sorted(exercices, reverse=True)


async def _executions_par_budget(exercice: int) -> dict[str, dict[str, float]]:
    """Montants exécutés par budget rattaché et par phase."""
    db = obtenir_database()
    par_budget: dict[str, dict[str, float]] = {}
    cursor = db[COLLECTION_EXECUTIONS].aggregate([
        {
            "$lookup": {
                "from": COLLECTION_BUDGETS,
                "localField": "budget_id",
                "foreignField": "_id",
                "as": "budget",
            }
        },
        {"$match": {"budget.exercice": exercice}},
        {
            "$group": {
                "_id": {"id_budget": "$budget_id", "phase": "$phase"},
                "total": {"$sum": "$montant"},
            }
        },
    ])
    async for doc in cursor:
        identifiant = str(doc["_id"]["id_budget"])
        phase = doc["_id"]["phase"]
        if phase not in PHASES_EXECUTION:
            continue
        par_budget.setdefault(identifiant, {})[phase] = _montant(doc, "total")
    return par_budget


async def _executions_mensuelles(exercice: int) -> dict[tuple[str, str], float]:
    """Montants exécutés par (mois, phase)."""
    db = obtenir_database()
    par_mois: dict[tuple[str, str], float] = {}
    cursor = db[COLLECTION_EXECUTIONS].aggregate([
        {
            "$lookup": {
                "from": COLLECTION_BUDGETS,
                "localField": "budget_id",
                "foreignField": "_id",
                "as": "budget",
            }
        },
        {"$match": {"budget.exercice": exercice}},
        {
            "$group": {
                "_id": {"mois": "$mois", "phase": "$phase"},
                "total": {"$sum": "$montant"},
            }
        },
    ])
    async for doc in cursor:
        mois = doc["_id"]["mois"]
        phase = doc["_id"]["phase"]
        if phase not in PHASES_EXECUTION:
            continue
        par_mois[(mois, phase)] = _montant(doc, "total")
    return par_mois


def _calculer_ligne(
    lfi: float,
    lfr: float,
    phases: dict[str, float],
) -> dict[str, Any]:
    credits = lfr if lfr > 0 else lfi
    engage = phases.get("engagement", 0.0)
    execute = phases.get(PHASE_FINALE, 0.0)
    variation = lfr - lfi
    return {
        "lfi": _acroissir(lfi),
        "lfr": _acroissir(lfr),
        "variation": _acroissir(variation),
        "variation_pct": round(variation / lfi, 6) if lfi > 0 else None,
        "credits": _acroissir(credits),
        "engagement": _acroissir(engage),
        "liquidation": _acroissir(phases.get("liquidation", 0.0)),
        "ordonnancement": _acroissir(phases.get("ordonnancement", 0.0)),
        "execute": _acroissir(execute),
        "disponible": _acroissir(max(0.0, credits - engage)),
        "solde": _acroissir(credits - execute),
        "taux_execution": round(execute / credits, 6) if credits > 0 else 0.0,
    }


async def _synthese_interne(exercice: int) -> dict[str, Any]:
    db = obtenir_database()
    par_budget = await _executions_par_budget(exercice)

    lignes: dict[str, dict[str, Any]] = {}
    cursor = db[COLLECTION_BUDGETS].find({"exercice": exercice})
    async for document in cursor:
        ligne = document["ligne_budgetaire"]
        if ligne not in lignes:
            lignes[ligne] = {
                "chapitre": document.get("chapitre", ""),
                "ligne_budgetaire": ligne,
                "libelle": document.get("libelle", ligne),
                "type": document.get("type", "inconnu"),
                "lfi": 0.0,
                "lfr": 0.0,
                "phases": {},
                "id_budget": str(document["_id"]),
            }
        nature = document.get("nature")
        montant = _montant(document, "montant_vote")
        if nature == NATURE_LFI:
            lignes[ligne]["lfi"] += montant
        elif nature == NATURE_LFR:
            lignes[ligne]["lfr"] += montant
        for phase, valeur in par_budget.get(str(document["_id"]), {}).items():
            lignes[ligne]["phases"][phase] = (
                lignes[ligne]["phases"].get(phase, 0.0) + valeur
            )

    details = [
        {
            **_calculer_ligne(donnees["lfi"], donnees["lfr"], donnees["phases"]),
            "chapitre": donnees["chapitre"],
            "ligne_budgetaire": donnees["ligne_budgetaire"],
            "libelle": donnees["libelle"],
            "type": donnees["type"],
        }
        for donnees in (lignes[cle] for cle in sorted(lignes))
    ]

    total = {
        "lfi": _acroissir(sum(detail["lfi"] for detail in details)),
        "lfr": _acroissir(sum(detail["lfr"] for detail in details)),
        "credits": _acroissir(sum(detail["credits"] for detail in details)),
        "engagement": _acroissir(sum(detail["engagement"] for detail in details)),
        "liquidation": _acroissir(sum(detail["liquidation"] for detail in details)),
        "ordonnancement": _acroissir(
            sum(detail["ordonnancement"] for detail in details)
        ),
        "execute": _acroissir(sum(detail["execute"] for detail in details)),
        "disponible": _acroissir(sum(detail["disponible"] for detail in details)),
        "solde": _acroissir(sum(detail["solde"] for detail in details)),
        "lignes_budgetaires": len(details),
    }
    total["variation"] = _acroissir(total["lfr"] - total["lfi"])
    total["variation_pct"] = (
        round(total["variation"] / total["lfi"], 6) if total["lfi"] > 0 else None
    )
    total["taux_execution"] = (
        round(total["execute"] / total["credits"], 6) if total["credits"] > 0 else 0.0
    )

    par_mois = await _executions_mensuelles(exercice)
    serie_mensuelle: list[dict[str, Any]] = []
    cumul = 0.0
    for mois in _mois_de_lexercice(exercice):
        paiement = par_mois.get((mois, PHASE_FINALE), 0.0)
        cumul += paiement
        serie_mensuelle.append({
            "mois": mois,
            "engagement": _acroissir(par_mois.get((mois, "engagement"), 0.0)),
            "liquidation": _acroissir(par_mois.get((mois, "liquidation"), 0.0)),
            "ordonnancement": _acroissir(par_mois.get((mois, "ordonnancement"), 0.0)),
            "paiement": _acroissir(paiement),
            "cumul": _acroissir(cumul),
        })

    repartition_par_type: list[dict[str, Any]] = []
    par_type: dict[str, dict[str, Any]] = {}
    for detail in details:
        entree = par_type.setdefault(
            detail["type"],
            {"type": detail["type"], "credits": 0.0, "execute": 0.0, "lignes": 0},
        )
        entree["credits"] += detail["credits"]
        entree["execute"] += detail["execute"]
        entree["lignes"] += 1
    for entree in par_type.values():
        entree["credits"] = _acroissir(entree["credits"])
        entree["execute"] = _acroissir(entree["execute"])
        entree["taux_execution"] = (
            round(entree["execute"] / entree["credits"], 6)
            if entree["credits"] > 0
            else 0.0
        )
        repartition_par_type.append(entree)
    repartition_par_type.sort(key=lambda item: item["execute"], reverse=True)

    return {
        "total": total,
        "lignes": details,
        "serie_mensuelle": serie_mensuelle,
        "repartition_par_type": repartition_par_type,
    }


def _comparer(
    exercice: int,
    courant: dict[str, Any],
    precedent: dict[str, Any],
) -> Optional[dict[str, Any]]:
    if precedent is None:
        return None
    retour = {
        "exercice_precedent": exercice - 1,
        "lfi_precedent": precedent["total"]["lfi"],
        "lfr_precedent": precedent["total"]["lfr"],
        "credits_precedent": precedent["total"]["credits"],
        "engage_precedent": precedent["total"]["engagement"],
        "execute_precedent": precedent["total"]["execute"],
        "disponible_precedent": precedent["total"]["disponible"],
        "solde_precedent": precedent["total"]["solde"],
        "taux_precedent": precedent["total"]["taux_execution"],
        "credits": courant["total"]["credits"],
        "execute": courant["total"]["execute"],
        "ecart_credits": _acroissir(
            courant["total"]["credits"] - precedent["total"]["credits"]
        ),
        "ecart_execute": _acroissir(
            courant["total"]["execute"] - precedent["total"]["execute"]
        ),
        "ecart_disponible": _acroissir(
            courant["total"]["disponible"] - precedent["total"]["disponible"]
        ),
        "ecart_solde": _acroissir(
            courant["total"]["solde"] - precedent["total"]["solde"]
        ),
    }
    if precedent["total"]["credits"] > 0:
        retour["variation_pct_credits"] = round(
            retour["ecart_credits"] / precedent["total"]["credits"], 6
        )
        retour["variation_pct_execute"] = round(
            retour["ecart_execute"] / precedent["total"]["execute"], 6
        ) if precedent["total"]["execute"] > 0 else None
    else:
        retour["variation_pct_credits"] = None
        retour["variation_pct_execute"] = None
    return retour


async def calculer_synthese(exercice: Optional[int] = None) -> dict[str, Any]:
    """Synthèse budgétaire détaillée d'un exercice.

    Si `exercice` est absent, l'exercice le plus récent est utilisé
    (sinon l'année courante). La comparaison porte sur l'exercice
    précédent lorsqu'il existe des crédits votés.
    """
    if exercice is None:
        disponibles = await exercices_budgetaires()
        exercice = disponibles[0] if disponibles else datetime.now(timezone.utc).year
    exercice = int(exercice)

    courant = await _synthese_interne(exercice)
    precedents = await exercices_budgetaires()
    precedent = (
        await _synthese_interne(exercice - 1) if (exercice - 1) in precedents else None
    )
    comparaison = _comparer(exercice, courant, precedent)

    return {
        "exercice": exercice,
        "calcule_le": datetime.now(timezone.utc).isoformat(),
        "total": courant["total"],
        "lignes": courant["lignes"],
        "serie_mensuelle": courant["serie_mensuelle"],
        "repartition_par_type": courant["repartition_par_type"],
        "comparaison": comparaison,
    }