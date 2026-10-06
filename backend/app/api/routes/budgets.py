"""Routes Budget : crédits votés, exécution par phase et indicateurs dérivés."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query

from app.security.permissions import exiger_permission
from app.services.budget_service import (
    calculer_synthese,
    exercices_budgetaires,
)

router = APIRouter()

_PERMISSION_VOIR = "budget:voir"


@router.get(
    "",
    summary="Synthèse budgétaire d'un exercice",
    description=(
        "Crédits LFI/LFR par ligne budgétaire, variation, exécution par phase "
        "(engagement, liquidation, ordonnancement, paiement), disponible, solde, "
        "taux d'exécution, série mensuelle, répartition par type et comparaison "
        "avec l'exercice précédent. Formules calculées côté backend."
    ),
)
async def synthese(
    exercice: Optional[int] = Query(
        None,
        ge=1900,
        le=2100,
        description="Exercice (défaut : le plus récent disponible).",
    ),
    _utilisateur: dict = Depends(exiger_permission(_PERMISSION_VOIR)),
):
    return await calculer_synthese(exercice=exercice)


@router.get(
    "/exercices",
    summary="Exercices disponibles (budget)",
    description="Exercices présents dans les crédits votés (ordre décroissant).",
)
async def exercices(
    _utilisateur: dict = Depends(exiger_permission(_PERMISSION_VOIR)),
):
    disponibles = await exercices_budgetaires()
    return {"exercices": disponibles}