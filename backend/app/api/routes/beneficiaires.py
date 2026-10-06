"""Routes Bénéficiaires : population, statistiques, filtres et comparaisons."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query

from app.security.permissions import exiger_permission
from app.services.beneficiaires_service import (
    exercices_population,
    lister_beneficiaires,
    statistiques_population,
)

router = APIRouter()

_PERMISSION_VOIR = "beneficiaires:voir"

_TRI_VALEURS = ("matricule", "nom", "prenom", "age", "situation", "date_naissance", "direction")
_ORDRE_VALEURS = ("asc", "desc")


@router.get(
    "/statistiques",
    summary="Statistiques de la population",
    description=(
        "Indicateurs de la population bénéficiaire d'un exercice : "
        "actifs, pensionnés, bénéficiaires RFM, tranches d'âge, "
        "répartitions et comparaison avec l'exercice précédent. Calcule "
        "depuis les collections métier ou, à défaut, depuis les "
        "importations normalisées (champ `source`)."
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
    return await statistiques_population(exercice=exercice)


@router.get(
    "/exercices",
    summary="Exercices disponibles (population)",
    description="Exercices présents dans la source de population (ordre décroissant).",
)
async def exercices(
    _utilisateur: dict = Depends(exiger_permission(_PERMISSION_VOIR)),
):
    disponibles = await exercices_population()
    return {"exercices": disponibles}


@router.get(
    "",
    summary="Lister les bénéficiaires",
    description=(
        "Liste paginée et filtrable de la population recensée : recherche "
        "(matricule/nom/prénom), situation, catégorie, genre, direction, "
        "statut de dossier, statut RFM, tri et pagination."
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
        None, max_length=80, description="Texte recherché sur matricule, nom ou prénom."
    ),
    situation: Optional[str] = Query(None, description="Situation : actif, pensionne, indeterminee."),
    categorie: Optional[str] = Query(None, description="Catégorie de bénéficiaire."),
    genre: Optional[str] = Query(None, description="Genre : M, F…"),
    direction: Optional[str] = Query(None, description="Direction administrative."),
    statut_dossier: Optional[str] = Query(None, description="Statut du dossier."),
    rfm: Optional[str] = Query(None, description="Bénéficiaire RFM : oui / non."),
    tri: str = Query("nom", description="Champ de tri."),
    ordre: str = Query("asc", description="Sens du tri : asc / desc."),
    limite: int = Query(50, ge=1, le=200, description="Nombre max de lignes."),
    saut: int = Query(0, ge=0, description="Nombre de lignes sautées (pagination)."),
    _utilisateur: dict = Depends(exiger_permission(_PERMISSION_VOIR)),
):
    if tri not in _TRI_VALEURS:
        tri = "nom"
    if ordre not in _ORDRE_VALEURS:
        ordre = "asc"

    def _texte(valeur) -> Optional[str]:
        if not isinstance(valeur, str):
            return None
        valeur = valeur.strip()
        return valeur or None

    def _entier(valeur, defaut: int) -> int:
        if isinstance(valeur, int):
            return valeur
        return defaut

    return await lister_beneficiaires(
        exercice=exercice,
        recherche=_texte(recherche),
        situation=_texte(situation),
        categorie=_texte(categorie),
        genre=_texte(genre),
        direction=_texte(direction),
        statut_dossier=_texte(statut_dossier),
        rfm=_texte(rfm),
        tri=tri,
        ordre=ordre,
        limite=_entier(limite, 50),
        saut=_entier(saut, 0),
    )