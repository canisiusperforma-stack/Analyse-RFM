"""Simulateur budgétaire.

Estime la consommation simplifiée « nombre de dossiers × montant moyen » et la
confronte à un budget hypothétique selon trois scénarios — prudent,
intermédiaire, élevé. Les résultats sont des hypothèses de travail, jamais des
prédictions certaines : le terme « scénario » est utilisé à dessein.
"""

from __future__ import annotations

from typing import Any

from app.schemas.simulation import RequeteSimulation
from app.utils.logging import get_logger

logger = get_logger(__name__)

AVERTISSEMENT = (
    "Les scénarios sont des hypothèses de travail et non des prédictions "
    "certaines : la consommation réelle dépendra de l'exécution, du nombre "
    "effectif de dossiers et du montant moyen réellement appliqué."
)

SCENARIOS = (
    {
        "cle": "prudent",
        "libelle": "Prudent",
        "description": "Scénario bas : les hypothèses sont réduites.",
    },
    {
        "cle": "intermediaire",
        "libelle": "Intermédiaire",
        "description": "Scénario central : hypothèses au niveau saisi.",
    },
    {
        "cle": "eleve",
        "libelle": "Élevé",
        "description": "Scénario haut : les hypothèses sont majorées.",
    },
)

_ECART_DOSSIERS_DEFAUT = 10
_ECART_MONTANT_DEFAUT = 5


def _coeficients(cle: str, ecart_dossiers: float, ecart_montant: float) -> tuple[float, float]:
    if cle == "prudent":
        return 1.0 - ecart_dossiers, 1.0 - ecart_montant
    if cle == "eleve":
        return 1.0 + ecart_dossiers, 1.0 + ecart_montant
    return 1.0, 1.0


def referentiel_simulations() -> dict[str, Any]:
    """Scénarios disponibles, valeurs par défaut et avertissement."""
    return {
        "scenarios": list(SCENARIOS),
        "defaults": {
            "ecart_dossiers_pct": _ECART_DOSSIERS_DEFAUT,
            "ecart_montant_pct": _ECART_MONTANT_DEFAUT,
        },
        "avertissement": AVERTISSEMENT,
    }


def calculer_simulation(requete: RequeteSimulation) -> dict[str, Any]:
    """Calcule la consommation estimée pour chaque scénario."""
    budget = round(requete.budget_hypothetique, 2)
    nombre = requete.nombre_dossiers
    montant = round(requete.montant_moyen, 2)
    ecart_dossiers = requete.ecart_dossiers_pct / 100.0
    ecart_montant = requete.ecart_montant_pct / 100.0

    consommation_centrale = round(nombre * montant, 2)

    scenarios: list[dict[str, Any]] = []
    for definition in SCENARIOS:
        coef_dossiers, coef_montant = _coeficients(
            definition["cle"], ecart_dossiers, ecart_montant
        )
        dossiers = max(1, int(round(nombre * coef_dossiers)))
        montant_scenario = round(montant * coef_montant, 2)
        consommation = round(dossiers * montant_scenario, 2)

        situation, taux, ecart_budget = _confronter_budget(
            consommation, budget
        )
        scenarios.append(
            {
                "cle": definition["cle"],
                "libelle": definition["libelle"],
                "sous_hypothese": _sous_hypothese(coef_dossiers, coef_montant),
                "nombre_dossiers": dossiers,
                "montant_moyen": montant_scenario,
                "consommation_estimee": consommation,
                "taux_consommation": taux,
                "ecart_budget": ecart_budget,
                "situation": situation,
            }
        )

    situation_centrale, taux_central, ecart_central = _confronter_budget(
        consommation_centrale, budget
    )

    return {
        "reference": {
            "budget_hypothetique": budget,
            "nombre_dossiers": nombre,
            "montant_moyen": montant,
            "consommation_centrale": consommation_centrale,
            "taux_consommation_central": taux_central,
            "ecart_budget_central": ecart_central,
            "situation_centrale": situation_centrale,
        },
        "ecarts_pct": {
            "dossiers": requete.ecart_dossiers_pct,
            "montant": requete.ecart_montant_pct,
        },
        "scenarios": scenarios,
        "avertissement": AVERTISSEMENT,
    }


def _confronter_budget(
    consommation: float, budget: float
) -> tuple[str, Any, float]:
    """Situation du scénario face au budget (dans les limites / dépassement)."""
    if budget <= 0:
        return "sans_budget", None, round(-consommation, 2)
    taux = round(consommation / budget, 4)
    ecart = round(budget - consommation, 2)
    situation = "depassement" if consommation > budget else "dans_le_budget"
    return situation, taux, ecart


def _sous_hypothese(coef_dossiers: float, coef_montant: float) -> str:
    signe_d = "+" if coef_dossiers > 1 else "−"
    signe_m = "+" if coef_montant > 1 else "−"
    if coef_dossiers == 1 and coef_montant == 1:
        return "Dossiers = hypothèse saisie, montant moyen = hypothèse saisie."
    return (
        f"Dossiers {signe_d}{round(abs(coef_dossiers - 1) * 100)} %, "
        f"montant moyen {signe_m}{round(abs(coef_montant - 1) * 100)} %."
    )