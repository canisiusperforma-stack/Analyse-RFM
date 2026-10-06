"""Schémas du module de prévision de la consommation budgétaire."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

PHASES_PREVISIONS = ("paiement", "engagement", "liquidation", "ordonnancement")

LABELS_PHASES = {
    "paiement": "Paiement",
    "engagement": "Engagement",
    "liquidation": "Liquidation",
    "ordonnancement": "Ordonnancement",
}


class RequetePrevision(BaseModel):
    """Paramètres d'une génération de prévision."""

    phase: str = Field(
        default="paiement",
        description="Phase d'exécution à prévoir (défaut : paiement).",
    )
    horizon: int = Field(
        default=6,
        ge=1,
        le=12,
        description="Nombre de mois à prévoir (1 à 12, défaut : 6).",
    )
    test_size: int = Field(
        default=4,
        ge=1,
        le=12,
        description="Nombre de mois retenus (fin de série) pour comparer les modèles.",
    )
    methode: Optional[str] = Field(
        default=None,
        description="Modèle imposé (optionnel) : moyenne_mobile, regression_lineaire, "
        "regression_saisonniere, arima ou prophet. Tous sont comparés si absent.",
    )