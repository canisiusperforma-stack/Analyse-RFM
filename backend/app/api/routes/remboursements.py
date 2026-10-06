"""Routes Remboursements : statistiques, filtres, recherche et pagination."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query

from app.security.permissions import exiger_permission
from app.services.remboursement_service import (
    exercices_remboursements,
    lister_remboursements,
    statistiques_remboursements,
)

router = APIRouter()

_PERMISSION_VOIR = "remboursements:voir"


def _texte(valeur) -> Optional[str]:
    if not isinstance(valeur, str):
        return None
    valeur = valeur.strip()
    return valeur or None


def _entier(valeur, defaut: int) -> int:
    if isinstance(valeur, int):
        return valeur
    return defaut


def _flottant(valeur, defaut=None) -> Optional[float]:
    if isinstance(valeur, (int, float)) and not isinstance(valeur, bool):
        return float(valeur)
    return defaut


@router.get(
    "/statistiques",
    summary="Statistiques des remboursements",
    description=(
        "Volumes par statut, montants (totaux, moyennes, médianes, "
        "minimums, maximums), répartitions par type de dépense et par "
        "circuit, série mensuelle et comparaison avec l'exercice précédent."
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
    return await statistiques_remboursements(exercice=exercice)


@router.get(
    "/exercices",
    summary="Exercices disponibles (remboursements)",
    description="Exercices présents dans les demandes (ordre décroissant).",
)
async def exercices(
    _utilisateur: dict = Depends(exiger_permission(_PERMISSION_VOIR)),
):
    disponibles = await exercices_remboursements()
    return {"exercices": disponibles}


@router.get(
    "",
    summary="Lister les demandes de remboursement",
    description=(
        "Liste paginée et filtrable : recherche (n° de dossier, matricule, "
        "nom ou prénom du bénéficiaire), statut, type de prestation, circuit, "
        "bornes de montant demandé, tri et pagination."
    ),
)
async def lister(
    exercice: Optional[int] = Query(
        None,
        ge=1900,
        le=2100,
        description="Exercice (défaut : le plus récent disponible).",
    ),
    recherche: Optional[str] = Query(
        None, max_length=80, description="N° de dossier, matricule, nom ou prénom."
    ),
    statut: Optional[str] = Query(
        None, description="Statut : soumis, en_attente, a_completer, valide, paye, refuse…"
    ),
    type_prestation: Optional[str] = Query(
        None, description="Type de dépense : soins, pharmacie, hospitalisation…"
    ),
    circuit: Optional[str] = Query(
        None, description="Circuit : circuit_normal, circuit_accelere."
    ),
    montant_min: Optional[float] = Query(
        None, ge=0, description="Montant demandé minimal."
    ),
    montant_max: Optional[float] = Query(
        None, ge=0, description="Montant demandé maximal."
    ),
    tri: str = Query("date_demande", description="Champ de tri."),
    ordre: str = Query("desc", description="Sens du tri : asc / desc."),
    limite: int = Query(50, ge=1, le=200, description="Nombre max de lignes."),
    saut: int = Query(0, ge=0, description="Nombre de lignes sautées (pagination)."),
    _utilisateur: dict = Depends(exiger_permission(_PERMISSION_VOIR)),
):
    return await lister_remboursements(
        exercice=exercice,
        recherche=_texte(recherche),
        statut=_texte(statut),
        type_prestation=_texte(type_prestation),
        circuit=_texte(circuit),
        montant_min=_flottant(montant_min),
        montant_max=_flottant(montant_max),
        tri=_texte(tri) or "date_demande",
        ordre=_texte(ordre) or "desc",
        limite=_entier(limite, 50),
        saut=_entier(saut, 0),
    )