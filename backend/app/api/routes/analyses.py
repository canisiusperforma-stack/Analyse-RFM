"""Routes Analyses : vue temporelle de la consommation des remboursements."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query

from app.security.permissions import exiger_permission
from app.services.analyse_service import (
    analyse_temporelle,
    statistiques_data_science,
)
from app.services.remboursement_service import exercices_remboursements

router = APIRouter()

_PERMISSION_VOIR = "analyses:voir"


@router.get(
    "/temporelle",
    summary="Analyse temporelle des remboursements",
    description=(
        "Série mensuelle (demandes, sommes demandées/remboursées, moyennes, "
        "taux d'exécution), variations d'un mois sur l'autre, synthèse "
        "annuelle et comparaison avec l'exercice précédent."
    ),
)
async def temporelle(
    exercice: Optional[int] = Query(
        None,
        ge=1900,
        le=2100,
        description="Exercice (défaut : le plus récent disponible).",
    ),
    _utilisateur: dict = Depends(exiger_permission(_PERMISSION_VOIR)),
):
    return await analyse_temporelle(exercice=exercice)


@router.get(
    "/statistiques",
    summary="Statistiques Descriptives (Pandas/NumPy)",
    description=(
        "Module Data Science : moyenne, médiane, variance, écart-type, "
        "quartiles, min/max, distributions (histogrammes), percentiles, "
        "corrélations de Pearson et comparaison actifs/pensionnés. "
        "Les calculs sont effectués avec Pandas et NumPy côté serveur."
    ),
)
async def statistiques(
    exercice: Optional[int] = Query(
        None,
        ge=1900,
        le=2100,
        description="Exercice (défaut : le plus récent disponible).",
    ),
    _utilisateur: dict = Depends(exiger_permission(_PERMISSION_VOIR)),
):
    return await statistiques_data_science(exercice=exercice)


@router.get(
    "/exercices",
    summary="Exercices disponibles (analyses)",
    description="Exercices présents dans les demandes (ordre décroissant).",
)
async def exercices(
    _utilisateur: dict = Depends(exiger_permission(_PERMISSION_VOIR)),
):
    disponibles = await exercices_remboursements()
    return {"exercices": disponibles}