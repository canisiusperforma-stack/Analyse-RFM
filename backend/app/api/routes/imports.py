from datetime import date, datetime
from typing import Any
from urllib.parse import quote

from bson import Decimal128, ObjectId
from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Query, UploadFile
from fastapi.responses import Response
from starlette import status

from app.imports import (
    ErreurImportation,
    OptionsImportation,
    importer_fichier,
    lire_fichier_original,
    lister_brutes,
    lister_importations,
    lister_nettoyees,
    lister_rejets,
    recuperer_importation,
)
from app.security.permissions import exiger_permission
from app.utils.logging import get_logger

router = APIRouter()

logger = get_logger(__name__)

_PERMISSION_IMPORTER = "importation:importer"
_PERMISSION_VOIR = "importation:voir_rapport"


def _parse_identifiant(identifiant: str) -> ObjectId:
    try:
        return ObjectId(identifiant)
    except Exception:
        raise HTTPException(
            status_code=422, detail="Identifiant d'importation invalide."
        )


def _parse_importe_par(valeur: str | None) -> ObjectId | None:
    if not valeur or not valeur.strip():
        return None
    try:
        return ObjectId(valeur.strip())
    except Exception:
        raise HTTPException(
            status_code=422,
            detail="En-tête X-Utilisateur-Id invalide (ObjectId attendu).",
        )


def _resume_liste(documents: list[dict]) -> list[dict]:
    resultats = []
    for doc in documents:
        rapport = doc.get("rapport") or {}
        resultats.append({
            "id": str(doc["_id"]),
            "nom_fichier": doc.get("nom_fichier"),
            "taille_octets": doc.get("taille_octets"),
            "importe_par": (
                str(doc["importe_par"]) if doc.get("importe_par") else None
            ),
            "importe_le": (
                doc["importe_le"].isoformat() if doc.get("importe_le") else None
            ),
            "statut": doc.get("statut"),
            "nb_lignes_total": rapport.get("nb_lignes_total", 0),
            "nb_lignes_importees": rapport.get("nb_lignes_importees", 0),
            "nb_lignes_rejetees": rapport.get("nb_lignes_rejetees", 0),
            "nb_doublons": rapport.get("nb_doublons", 0),
        })
    return resultats


def _serialiser_valeur(valeur: Any) -> Any:
    """Convertit les valeurs BSON en types JSON sérialisables."""
    if isinstance(valeur, Decimal128):
        return float(valeur.to_decimal())
    if isinstance(valeur, datetime):
        return valeur.isoformat()
    if isinstance(valeur, date):
        return valeur.isoformat()
    if isinstance(valeur, ObjectId):
        return str(valeur)
    if isinstance(valeur, dict):
        return {cle: _serialiser_valeur(val) for cle, val in valeur.items()}
    if isinstance(valeur, (list, tuple)):
        return [_serialiser_valeur(val) for val in valeur]
    return valeur


def _serialiser_lignes(documents: list[dict]) -> list[dict]:
    resultats = []
    for doc in documents:
        valeurs = doc.get("valeurs") or {}
        ligne = {
            "ligne": doc.get("ligne"),
            "feuille": doc.get("feuille", 0),
            "valeurs": _serialiser_valeur(valeurs),
        }
        if "manquantes" in doc:
            ligne["manquantes"] = doc.get("manquantes") or []
        resultats.append(ligne)
    return resultats


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Importer un fichier de données RFM",
    description=(
        "Reçoit un fichier CSV ou XLSX, applique le pipeline de validation "
        "et de normalisation, puis conserve données brutes, données "
        "nettoyées, lignes rejetées et rapport d'importation."
    ),
)
async def importer(
    fichier: UploadFile = File(..., description="Fichier .csv ou .xlsx"),
    encodage: str | None = Form(
        None, description="Encodage forcé (ex. utf-8, latin-1)."
    ),
    delimiteur: str | None = Form(
        None, description="Séparateur CSV forcé (ex. ';')."
    ),
    feuille: int = Form(
        0, description="Index de la feuille Excel à lire (défaut 0)."
    ),
    colonnes_obligatoires: str | None = Form(
        None,
        description="Colonnes obligatoires (noms normalisés séparés par des virgules).",
    ),
    deversement: bool = Form(
        False,
        description=(
            "Déverse les feuilles reconnues vers les collections métier "
            "(beneficiaires, budgets_rfm, executions, remboursements)."
        ),
    ),
    x_utilisateur_id: str | None = Header(
        None, alias="X-Utilisateur-Id", description="Id de l'utilisateur (traçabilité)."
    ),
    _utilisateur: dict = Depends(exiger_permission(_PERMISSION_IMPORTER)),
):
    contenu = await fichier.read()

    importe_par = _parse_importe_par(x_utilisateur_id) or _utilisateur.get(
        "_id"
    )

    obligatoires = [
        c.strip()
        for c in (colonnes_obligatoires or "").split(",")
        if c.strip()
    ]

    options = OptionsImportation(
        encodage=encodage or None,
        delimiteur=delimiteur or None,
        feuille=feuille,
        colonnes_obligatoires=obligatoires,
        deversement=deversement,
    )

    try:
        return await importer_fichier(
            contenu,
            fichier.filename or "fichier_inconnu",
            importe_par=importe_par,
            options=options,
        )
    except ErreurImportation as erreur:
        logger.warning("Import refusé : %s", erreur)
        raise HTTPException(status_code=422, detail=erreur.message)
    except Exception as erreur:
        logger.exception("Erreur inattendue lors de l'import : %s", erreur)
        raise HTTPException(
            status_code=500,
            detail=str(getattr(erreur, "message", erreur)),
        )


@router.get(
    "",
    summary="Lister les importations",
    description="Historique des importations : qui, quand, quel fichier, compteurs.",
)
async def lister(
    limite: int = Query(50, ge=1, le=500),
    saut: int = Query(0, ge=0),
    _utilisateur: dict = Depends(exiger_permission(_PERMISSION_VOIR)),
):
    documents = await lister_importations(limite=limite, saut=saut)
    return {"total_affichés": len(documents), "importations": _resume_liste(documents)}


@router.get(
    "/{identifiant}",
    summary="Détail d'une importation",
    description="Métadonnées, rapport d'importation et fichier associé.",
)
async def detail(
    identifiant: str,
    _utilisateur: dict = Depends(exiger_permission(_PERMISSION_VOIR)),
):
    id_import = _parse_identifiant(identifiant)
    doc = await recuperer_importation(id_import)
    if doc is None:
        raise HTTPException(status_code=404, detail="Importation introuvable.")

    rapport = doc.get("rapport") or {}
    return {
        "id": str(doc["_id"]),
        "nom_fichier": doc.get("nom_fichier"),
        "taille_octets": doc.get("taille_octets"),
        "sha256": doc.get("sha256"),
        "type_mime": doc.get("type_mime"),
        "fichier_id": str(doc["fichier_id"]) if doc.get("fichier_id") else None,
        "importe_par": (
            str(doc["importe_par"]) if doc.get("importe_par") else None
        ),
        "importe_le": (
            doc["importe_le"].isoformat() if doc.get("importe_le") else None
        ),
        "statut": doc.get("statut"),
        "erreur": doc.get("erreur"),
        "rapport": rapport,
    }


@router.get(
    "/{identifiant}/rejets",
    summary="Lignes rejetées d'une importation",
    description="Détail des lignes rejetées et de leurs motifs de rejet.",
)
async def rejets(
    identifiant: str,
    limite: int = Query(200, ge=1, le=1000),
    saut: int = Query(0, ge=0),
    _utilisateur: dict = Depends(exiger_permission(_PERMISSION_VOIR)),
):
    id_import = _parse_identifiant(identifiant)
    doc = await recuperer_importation(id_import)
    if doc is None:
        raise HTTPException(status_code=404, detail="Importation introuvable.")

    documents = await lister_rejets(id_import, limite=limite, saut=saut)
    resultats = []
    for rejet in documents:
        resultats.append({
            "ligne": rejet.get("ligne"),
            "feuille": rejet.get("feuille", 0),
            "colonne": rejet.get("colonne"),
            "valeur": rejet.get("valeur"),
            "raison": rejet.get("raison"),
            "type_erreur": rejet.get("type_erreur"),
        })
    return {"total": len(resultats), "rejets": resultats}


@router.get(
    "/{identifiant}/brutes",
    summary="Lignes brutes d'une importation",
    description="Lignes conservées telles qu'importées (jamais modifiées).",
)
async def brutes(
    identifiant: str,
    limite: int = Query(200, ge=1, le=1000),
    saut: int = Query(0, ge=0),
    _utilisateur: dict = Depends(exiger_permission(_PERMISSION_VOIR)),
):
    id_import = _parse_identifiant(identifiant)
    doc = await recuperer_importation(id_import)
    if doc is None:
        raise HTTPException(status_code=404, detail="Importation introuvable.")

    documents = await lister_brutes(id_import, limite=limite, saut=saut)
    return {"total": len(documents), "lignes": _serialiser_lignes(documents)}


@router.get(
    "/{identifiant}/nettoyees",
    summary="Lignes nettoyées d'une importation",
    description="Lignes après normalisation (montants, dates, types).",
)
async def nettoyees(
    identifiant: str,
    limite: int = Query(200, ge=1, le=1000),
    saut: int = Query(0, ge=0),
    _utilisateur: dict = Depends(exiger_permission(_PERMISSION_VOIR)),
):
    id_import = _parse_identifiant(identifiant)
    doc = await recuperer_importation(id_import)
    if doc is None:
        raise HTTPException(status_code=404, detail="Importation introuvable.")

    documents = await lister_nettoyees(id_import, limite=limite, saut=saut)
    return {"total": len(documents), "lignes": _serialiser_lignes(documents)}


@router.get(
    "/{identifiant}/fichier",
    summary="Télécharger le fichier d'origine",
    description="Fichier original stocké dans GridFS, jamais modifié.",
)
async def telecharger_fichier(
    identifiant: str,
    _utilisateur: dict = Depends(exiger_permission(_PERMISSION_VOIR)),
):
    id_import = _parse_identifiant(identifiant)
    doc = await recuperer_importation(id_import)
    if doc is None:
        raise HTTPException(status_code=404, detail="Importation introuvable.")

    fichier_id = doc.get("fichier_id")
    if fichier_id is None:
        raise HTTPException(
            status_code=404, detail="Aucun fichier associé à cette importation."
        )

    contenu = await lire_fichier_original(fichier_id)
    nom_fichier = doc.get("nom_fichier") or "fichier"
    type_mime = doc.get("type_mime") or "application/octet-stream"

    disposition = (
        f"attachment; filename=\"{nom_fichier}\"; "
        f"filename*=UTF-8''{quote(nom_fichier)}"
    )
    return Response(
        content=contenu,
        media_type=type_mime,
        headers={"Content-Disposition": disposition},
    )