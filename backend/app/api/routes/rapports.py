"""Routes Rapports : rapport consolidé par exercice et export Excel structuré.

Trois points de terminaison :
- `GET  /api/v1/rapports/exercices`       exercices pour lesquels un rapport existe ;
- `GET  /api/v1/rapports/{exercice}`      rapport JSON complet (web) ;
- `GET  /api/v1/rapports/{exercice}/excel` classeur `.xlsx` à télécharger.

L'export sert un fichier Excel réellement valide (openpyxl), nommé
`Rapport_RFM_{exercice}_Export_Structuré.xlsx`.
"""

from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Path, Response

from app.reports.excel_generator import generer_classeur_exercice
from app.security.permissions import exiger_permission
from app.services.rapport_service import collecter_rapport, exercices_disponibles

router = APIRouter()

_PERMISSION_VOIR = "rapports:voir"
_PERMISSION_EXPORTER = "rapports:exporter"

_TYPE_MIME_XLSX = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)


def _nom_fichier_excel(exercice: int) -> str:
    return f"Rapport_RFM_{exercice}_Export_Structuré.xlsx"


@router.get(
    "/exercices",
    summary="Exercices disposant d'un rapport",
    description=(
        "Exercices pour lesquels des données existent (crédits votés ou "
        "demandes de remboursement), ordre décroissant."
    ),
)
async def exercices(
    _utilisateur: dict = Depends(exiger_permission(_PERMISSION_VOIR)),
):
    disponibles = await exercices_disponibles()
    return {"exercices": disponibles}


@router.get(
    "/{exercice}",
    summary="Rapport consolidé d'un exercice",
    description=(
        "Indicateurs bruts agrégés pour l'exercice : population, budget "
        "(lignes, série mensuelle, répartition par type), remboursements et "
        "résumé analytique. Aucun chiffre n'est figé côté frontend."
    ),
)
async def rapport(
    exercice: int = Path(..., ge=1900, le=2100),
    _utilisateur: dict = Depends(exiger_permission(_PERMISSION_VOIR)),
):
    if exercice not in await exercices_disponibles():
        raise HTTPException(
            status_code=404,
            detail=f"Aucune donnée pour l'exercice {exercice}.",
        )
    return await collecter_rapport(exercice)


@router.get(
    "/{exercice}/excel",
    summary="Exporter le rapport d'un exercice en Excel",
    description=(
        "Classeur `.xlsx` multi-feuilles (Synthèse, Bénéficiaires, Budget, "
        "Exécution, Remboursements, Résumé analytique) généré par openpyxl et "
        "téléchargeable immédiatement."
    ),
)
async def export_excel(
    exercice: int = Path(..., ge=1900, le=2100),
    _utilisateur: dict = Depends(exiger_permission(_PERMISSION_EXPORTER)),
):
    if exercice not in await exercices_disponibles():
        raise HTTPException(
            status_code=404,
            detail=f"Aucune donnée pour l'exercice {exercice}.",
        )
    donnees = await collecter_rapport(exercice)
    contenu = generer_classeur_exercice(exercice, donnees).getvalue()

    nom = _nom_fichier_excel(exercice)
    disposition = (
        f"attachment; filename=\"{nom}\"; "
        f"filename*=UTF-8''{quote(nom)}"
    )
    return Response(
        content=contenu,
        media_type=_TYPE_MIME_XLSX,
        headers={"Content-Disposition": disposition},
    )