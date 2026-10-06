"""Routes Simulations : simulateur budgétaire par scénarios."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.schemas.simulation import RequeteSimulation
from app.security.permissions import exiger_permission
from app.services.simulation_service import (
    calculer_simulation,
    referentiel_simulations,
)

router = APIRouter()

_PERMISSION_VOIR = "simulations:voir"
_PERMISSION_CREER = "simulations:creer"


@router.get(
    "/scenarios",
    summary="Scénarios disponibles",
    description=(
        "Référentiel des scénarios (prudent, intermédiaire, élevé), valeurs par "
        "défaut des écarts et avertissement : les scénarios sont des hypothèses "
        "de travail, pas des prédictions certaines."
    ),
)
def scenarios(
    _utilisateur: dict = Depends(exiger_permission(_PERMISSION_VOIR)),
):
    return referentiel_simulations()


@router.post(
    "/calculer",
    summary="Calculer la consommation estimée par scénario",
    description=(
        "Estime la consommation « nombre de dossiers × montant moyen » pour "
        "chaque scénario (prudent, intermédiaire, élevé) et la confronte au "
        "budget hypothétique (taux de consommation, écart, dépassement éventuel)."
    ),
)
def calculer(
    requete: RequeteSimulation,
    _utilisateur: dict = Depends(exiger_permission(_PERMISSION_CREER)),
):
    return calculer_simulation(requete)