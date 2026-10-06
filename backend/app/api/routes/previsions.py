"""Routes Prévisions : prévision de la consommation budgétaire RFM."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query

from app.schemas.prevision import RequetePrevision
from app.security.permissions import exiger_permission
from app.services.prevision_service import (
    charger_serie,
    generer_prevision,
    referentiel_previsions,
)
from app.utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter()

_PERMISSION_VOIR = "previsions:voir"
_PERMISSION_CREER = "previsions:creer"


@router.get(
    "/meta",
    summary="Référentiel de prévision",
    description=(
        "Phases disponibles, modèles tests (libellés, descriptions), seuils de "
        "suffisance des données et bibliothèques ML disponibles."
    ),
)
def meta(
    _utilisateur: dict = Depends(exiger_permission(_PERMISSION_VOIR)),
):
    return referentiel_previsions()


@router.get(
    "/donnees",
    summary="Données temporelles disponibles",
    description=(
        "Série mensuelle d'exécution d'une phase (défaut : paiement) avec "
        "totaux et cumul annuel — permet d'apprécier la quantité de données "
        "avant de lancer une prévision. Sans prévision générée."
    ),
)
async def donnees(
    phase: Optional[str] = Query(
        None, description="Phase d'exécution (défaut : paiement)."
    ),
    _utilisateur: dict = Depends(exiger_permission(_PERMISSION_VOIR)),
):
    mois, valeurs = await charger_serie(phase or "paiement")
    return {
        "phase": phase or "paiement",
        "points": len(mois),
        "exercices": sorted({int(m[:4]) for m in mois}) if mois else [],
        "premier_mois": mois[0] if mois else None,
        "dernier_mois": mois[-1] if mois else None,
        "serie_mensuelle": [
            {"mois": m, "valeur": v} for m, v in zip(mois, valeurs)
        ],
    }


@router.post(
    "/generer",
    summary="Générer une prévision de consommation",
    description=(
        "Charge l'historique mensuel (phase, défaut : paiement), compare les "
        "modèles disponibles sur une fenêtre de validation, sélectionne le "
        "meilleur (RMSE puis MAE) et produit prévisions, intervalles 80 %/95 %, "
        "métriques et limites. Les résultats restent expérimentaux tant que "
        "l'historique est court."
    ),
)
async def generer(
    requete: RequetePrevision,
    _utilisateur: dict = Depends(exiger_permission(_PERMISSION_CREER)),
):
    return await generer_prevision(
        phase=requete.phase,
        horizon=requete.horizon,
        test_size=requete.test_size,
        methode=requete.methode,
    )