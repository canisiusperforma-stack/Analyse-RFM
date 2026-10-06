"""Routes Anomalies : détection d'observations atypiques et vérification.

Fournit :
- un référentiel (méthodes, variables, niveaux, statuts de vérification) ;
- l'exécution de la détection (IQR, z-score, Isolation Forest, éventuellement
  LOF) selon la nature des données disponibles ;
- la comparaison des méthodes pour chaque observation signalée ;
- la liste filtrable/paginée et le workflow de vérification humaine.

Précautions : aucune observation n'est jamais qualifiée automatiquement de
fraude ; le lexique se limite à « observation atypique », « anomalie
potentielle » et « valeur à vérifier ».
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, Query

from app.schemas.anomalie import RequeteDetection, RequeteVerification
from app.security.permissions import exiger_permission
from app.services.anomalie_service import (
    detecter_anomalies,
    lister_anomalies,
    mettre_a_jour_verification,
    recuperer_anomalie,
    referentiel_anomalies,
)
from app.services.remboursement_service import exercices_remboursements

router = APIRouter()

_PERMISSION_VOIR = "anomalies:voir"
_PERMISSION_TRAITER = "anomalies:traiter"


@router.get(
    "/exercices",
    summary="Exercices disponibles (anomalies)",
    description="Exercices présents dans les demandes (ordre décroissant).",
)
async def exercices(
    _utilisateur: dict = Depends(exiger_permission(_PERMISSION_VOIR)),
):
    disponibles = await exercices_remboursements()
    return {"exercices": disponibles}


@router.get(
    "/meta",
    summary="Référentiel de la détection",
    description=(
        "Méthodes disponibles (IQR, z-score, Isolation Forest, LOF) avec leurs "
        "paramètres, variables analysables, niveaux d'alerte et statuts du "
        "workflow de vérification — pour configurer l'interface."
    ),
)
async def meta(
    _utilisateur: dict = Depends(exiger_permission(_PERMISSION_VOIR)),
):
    return referentiel_anomalies()


@router.post(
    "/detection",
    summary="Lancer la détection d'observations atypiques",
    description=(
        "Analyse les remboursements d'un exercice selon la nature des données : "
        "IQR, z-score, Isolation Forest et Local Outlier Factor (si adapté). "
        "Chaque observation signalée est décrite par sa valeur, son score, son "
        "niveau (« observation atypique », « anomalie potentielle », « valeur à "
        "vérifier ») et une justification. Les alertes sont persistées par défaut "
        "pour alimenter le workflow de vérification. Aucune observation n'est "
        "jamais qualifiée automatiquement de fraude."
    ),
)
async def detection(
    requete: RequeteDetection,
    _utilisateur: dict = Depends(exiger_permission(_PERMISSION_VOIR)),
):
    parametres: Optional[dict[str, Any]] = None
    if requete.parametres is not None:
        parametres = requete.parametres.model_dump(exclude_none=True)
    return await detecter_anomalies(
        exercice=requete.exercice,
        variables=requete.variables,
        methodes=requete.methodes,
        parametres=parametres,
        stocker=requete.stocker,
    )


@router.get(
    "",
    summary="Liste des observations atypiques",
    description=(
        "Alertes persistées, filtrables par exercice, statut de vérification, "
        "niveau, méthode ou variable, avec recherche (n° de dossier, bénéficiaire, "
        "justification), tri et pagination. Les comptes par statut/niveau/méthode "
        "sont fournis pour la synthèse."
    ),
)
async def liste(
    exercice: Optional[int] = Query(
        None, ge=1900, le=2100, description="Exercice (défaut : tous)."
    ),
    statut_verification: Optional[str] = Query(
        None, description="Statut du workflow de vérification."
    ),
    niveau: Optional[str] = Query(None, description="Niveau d'alerte."),
    methode: Optional[str] = Query(None, description="Méthode signalante."),
    variable: Optional[str] = Query(None, description="Variable analysée."),
    recherche: Optional[str] = Query(None, description="Recherche libre."),
    tri: str = Query("detecte_le", description="Colonne de tri."),
    ordre: str = Query("desc", description="asc ou desc."),
    limite: int = Query(25, ge=1, le=100),
    saut: int = Query(0, ge=0),
    _utilisateur: dict = Depends(exiger_permission(_PERMISSION_VOIR)),
):
    return await lister_anomalies(
        exercice=exercice,
        statut_verification=statut_verification,
        niveau=niveau,
        methode=methode,
        variable=variable,
        recherche=recherche,
        tri=tri,
        ordre=ordre,
        limite=limite,
        saut=saut,
    )


@router.get(
    "/{anomalie_id}",
    summary="Détail d'une observation atypique",
    description="Alerte persistée complète, y compris la comparaison des méthodes.",
)
async def detail(
    anomalie_id: str,
    _utilisateur: dict = Depends(exiger_permission(_PERMISSION_VOIR)),
):
    return await recuperer_anomalie(anomalie_id)


@router.patch(
    "/{anomalie_id}/verification",
    summary="Mettre à jour le statut de vérification",
    description=(
        "Statut témoigné par un humain (à vérifier, en cours, atypicité "
        "confirmée, écartée) avec commentaire. La modification est tracée "
        "(utilisateur, horodatage)."
    ),
)
async def verification(
    anomalie_id: str,
    requete: RequeteVerification,
    utilisateur: dict = Depends(exiger_permission(_PERMISSION_TRAITER)),
):
    return await mettre_a_jour_verification(
        anomalie_id=anomalie_id,
        statut_verification=requete.statut_verification,
        commentaire=requete.commentaire,
        utilisateur=utilisateur,
    )