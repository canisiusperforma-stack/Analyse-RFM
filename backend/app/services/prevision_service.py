"""Service de prévision de la consommation budgétaire.

Charge les exécutions mensuelles (par phase) et les confie au module
`app.ml.forecasting` pour produire prévisions, intervalles, historique,
métriques et limites du modèle retenu.
"""

from __future__ import annotations

import importlib.util
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional

from app.database import obtenir_database
from app.ml import forecasting
from app.schemas.prevision import LABELS_PHASES, PHASES_PREVISIONS
from app.utils.logging import get_logger

logger = get_logger(__name__)

COLLECTION_EXECUTIONS = "executions"

_PHASE_DEFAUT = "paiement"


def _montant(valeur: Any) -> float:
    if isinstance(valeur, Decimal):
        return float(valeur)
    if hasattr(valeur, "to_decimal"):
        return float(valeur.to_decimal())
    return float(valeur or 0)


def statsmodels_disponible() -> bool:
    return importlib.util.find_spec("statsmodels") is not None


def referentiel_previsions() -> dict[str, Any]:
    """Référentiel statique : phases, modèles, seuils, paramètres par défaut."""
    return {
        "phases": [
            {"cle": cle, "libelle": LABELS_PHASES[cle]}
            for cle in PHASES_PREVISIONS
        ],
        "phase_par_defaut": _PHASE_DEFAUT,
        "modeles": [
            {
                "cle": cle,
                "libelle": forecasting.LABELS_MODELES[cle],
                "description": forecasting.DESCRIPTIONS_MODELES[cle],
            }
            for cle in forecasting.MODELES
        ],
        "seuils_suffisance": forecasting.evaluer_suffisance(
            forecasting.MINIMUM_MOIS_INSUFFISANT, 1
        )["seuils"],
        "defauts": {
            "horizon": forecasting.DEFAUT_HORIZON,
            "test_size": forecasting.DEFAUT_TAILLE_TEST,
            "fenetre_moyenne_mobile": forecasting.MOIS_FENETRE_MOYENNE_MOBILE,
        },
        "bibliotheques": {
            "statsmodels": statsmodels_disponible(),
            "prophet": importlib.util.find_spec("prophet") is not None,
        },
    }


async def charger_serie(phase: str = _PHASE_DEFAUT) -> tuple[list[str], list[float]]:
    """Charge les totaux mensuels d'exécution d'une phase, tous exercices."""
    if phase not in PHASES_PREVISIONS:
        phase = _PHASE_DEFAUT
    executions = obtenir_database()[COLLECTION_EXECUTIONS]
    mois_serie: dict[str, float] = {}
    curseur = executions.find(
        {"phase": phase, "mois": {"$exists": True, "$ne": ""}},
        {"mois": 1, "montant": 1},
    )
    async for doc in curseur:
        mois = doc.get("mois")
        if not mois or not isinstance(mois, str):
            continue
        if len(mois) != 7 or mois[4] != "-":
            continue
        montant = _montant(doc.get("montant", 0))
        mois_serie[mois] = mois_serie.get(mois, 0.0) + montant

    mois = sorted(mois_serie)
    valeurs = [round(mois_serie[m], 2) for m in mois]
    return mois, valeurs


def _serie_avec_cumul(
    mois: list[str], valeurs: list[float]
) -> list[dict[str, Any]]:
    """Historique mensuel avec cumul annuel (remis à zéro chaque exercice)."""
    serie: list[dict[str, Any]] = []
    annee_precedente: Optional[str] = None
    cumul = 0.0
    for i, m in enumerate(mois):
        annee = m[:4]
        if annee != annee_precedente:
            cumul = 0.0
            annee_precedente = annee
        cumul += valeurs[i]
        serie.append(
            {
                "mois": m,
                "annee": annee,
                "valeur": valeurs[i],
                "cumul": round(cumul, 2),
            }
        )
    return serie


async def generer_prevision(
    phase: str = _PHASE_DEFAUT,
    horizon: int = forecasting.DEFAUT_HORIZON,
    test_size: int = forecasting.DEFAUT_TAILLE_TEST,
    methode: Optional[str] = None,
) -> dict[str, Any]:
    """Prévision complète de la consommation mensuelle d'une phase."""
    if phase not in PHASES_PREVISIONS:
        phase = _PHASE_DEFAUT

    mois, valeurs = await charger_serie(phase)
    if methode and methode not in forecasting.MODELES:
        methode = None

    resultat = forecasting.generer_forecast(
        mois,
        valeurs,
        horizon=int(horizon),
        test_size=int(test_size),
        methode=methode,
    )

    resultat["calcule_le"] = datetime.now(timezone.utc).isoformat()
    resultat["phase"] = phase
    resultat["libelle_phase"] = LABELS_PHASES[phase]
    resultat["serie_mensuelle"] = _serie_avec_cumul(mois, valeurs)
    resultat["total_historique"] = (
        round(sum(valeurs), 2) if valeurs else None
    )
    return resultat