"""Schémas du simulateur budgétaire."""

from __future__ import annotations

from pydantic import BaseModel, Field


class RequeteSimulation(BaseModel):
    """Hypothèses saisies par l'utilisateur pour le simulateur.

    Le simulateur estime une consommation
    « nombre de dossiers × montant moyen » et la confronte à un budget
    hypothétique, selon trois scénarios (prudent, intermédiaire, élevé).
    Ce sont des hypothèses de travail, pas des prédictions certaines.
    """

    budget_hypothetique: float = Field(
        default=0,
        ge=0,
        description="Budget disponible (Ar) pour la période considérée.",
    )
    nombre_dossiers: int = Field(
        default=0,
        ge=1,
        description="Nombre de dossiers attendu sur la période.",
    )
    montant_moyen: float = Field(
        default=0,
        ge=0,
        description="Montant moyen estimé par dossier (Ar).",
    )
    ecart_dossiers_pct: int = Field(
        default=10,
        ge=1,
        le=50,
        description="Écart du nombre de dossiers entre scénarios (%), autour de l'hypothèse centrale.",
    )
    ecart_montant_pct: int = Field(
        default=5,
        ge=1,
        le=50,
        description="Écart du montant moyen entre scénarios (%), autour de l'hypothèse centrale.",
    )