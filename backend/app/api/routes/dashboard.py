"""Routes du tableau de bord : synthèse des indicateurs par exercice."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query

from app.security.permissions import exiger_permission
from app.services.dashboard_service import analyser_exercices, calculer_synthese

router = APIRouter()

_PERMISSION_VOIR = "dashboard:voir"


@router.get(
    "/synthese",
    summary="Synthèse du tableau de bord",
    description=(
        "Renvoie les indicateurs clés (population, budget, remboursements), "
        "les séries mensuelles pour les graphiques et un résumé analytique, "
        "le tout calculé par le backend pour l'exercice demandé. Aucune "
        "valeur n'est codée en dur côté frontend."
    ),
)
async def synthese(
    exercice: Optional[int] = Query(
        None,
        ge=1900,
        le=2100,
        description="Exercice budgétaire (défaut : le plus récent en base).",
    ),
    _utilisateur: dict = Depends(exiger_permission(_PERMISSION_VOIR)),
):
    return await calculer_synthese(exercice=exercice)


@router.get(
    "/exercices",
    summary="Exercices disponibles",
    description="Exercices budgétaires présents en base (ordre décroissant).",
)
async def exercices(
    _utilisateur: dict = Depends(exiger_permission(_PERMISSION_VOIR)),
):
    disponibles = await analyser_exercices()
    return {"exercices": disponibles}