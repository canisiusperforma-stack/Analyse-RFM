"""Orchestration d'une importation de fichier de données RFM."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from bson import ObjectId

from app.database import obtenir_database
from app.imports.cibles import CIBLES, cible_pour_feuille
from app.imports.colonnes import (
    analyser_colonnes,
    lister_feuilles,
    lire_fichier,
)
from app.imports.deversement import deverser
from app.imports.erreurs import ErreurImportation
from app.imports.models import (
    ColonneAnalysee,
    OptionsImportation,
    RejetImportation,
    RapportImportation,
)
from app.imports.stockage import (
    COLLECTION_IMPORTATIONS,
    assurer_indexes,
    finaliser_importation,
    inserer_brutes,
    inserer_importation,
    inserer_nettoyees,
    inserer_rejets,
    sauvegarder_fichier_original,
)
from app.imports.validation import marquer_doublons, valider_lignes
from app.utils.logging import get_logger

logger = get_logger(__name__)

TAILLE_MAX_OCTETS = 50 * 1024 * 1024

EXTENSIONS_AUTORISEES = {
    ".csv": "text/csv",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


async def importer_fichier(
    contenu: bytes,
    nom_fichier: str,
    *,
    importe_par: Optional[ObjectId] = None,
    options: Optional[OptionsImportation] = None,
) -> dict:
    """
    Importe un fichier CSV/XLSX via le pipeline complet.

    Déroulé :
    1. contrôles (taille, extension) ;
    2. stockage du fichier original (GridFS, jamais modifié) ;
    3. lecture + détection des colonnes/types ;
    4. validation + normalisation de chaque ligne ;
    5. détection des doublons ;
    6. conservation : brut (chaque ligne), nettoyé (lignes retenues),
       rejets (lignes rejetées + motifs) ;
    7. rapport d'importation intégré aux métadonnées.
    """
    options = options or OptionsImportation()

    if not contenu:
        raise ErreurImportation("Le fichier est vide.")

    if len(contenu) > TAILLE_MAX_OCTETS:
        raise ErreurImportation(
            f"Fichier trop volumineux ({len(contenu)} octets). "
            f"Taille maximale : {TAILLE_MAX_OCTETS} octets."
        )

    extension = _extension(nom_fichier)
    if extension not in EXTENSIONS_AUTORISEES:
        raise ErreurImportation(
            f"Format non supporté : '{extension}'. "
            f"Formats autorisés : {', '.join(EXTENSIONS_AUTORISEES)}."
        )

    await assurer_indexes()
    digest = hashlib.sha256(contenu).hexdigest()
    importation_id = ObjectId()
    importe_le = datetime.now(timezone.utc)

    document_meta = {
        "nom_fichier": nom_fichier,
        "taille_octets": len(contenu),
        "sha256": digest,
        "type_mime": EXTENSIONS_AUTORISEES[extension],
        "importe_par": importe_par,
        "importe_le": importe_le,
        "statut": "en_cours",
        "erreur": None,
        "rapport": None,
    }
    await inserer_importation(importation_id, document_meta)

    try:
        fichier_id = await sauvegarder_fichier_original(
            contenu,
            nom_fichier,
            EXTENSIONS_AUTORISEES[extension],
            digest,
        )
        await obtenir_database()[COLLECTION_IMPORTATIONS].update_one(
            {"_id": importation_id},
            {"$set": {"fichier_id": fichier_id}},
        )

        rapport = await _traiter(
            contenu=contenu,
            nom_fichier=nom_fichier,
            importation_id=importation_id,
            options=options,
            digest=digest,
        )

        await finaliser_importation(importation_id, "termine", rapport=rapport)
        logger.info(
            "Importation '%s' terminée : %s lignes, %s retenues, %s rejetées",
            nom_fichier,
            rapport["nb_lignes_total"],
            rapport["nb_lignes_importees"],
            rapport["nb_lignes_rejetees"],
        )
        return await _ressource_importation(importation_id)

    except Exception as erreur:
        logger.error("Importation '%s' échouée : %s", nom_fichier, erreur)
        await finaliser_importation(
            importation_id,
            "echec",
            erreur=str(erreur),
        )
        raise


def _planifier_feuilles(
    contenu: bytes,
    nom_fichier: str,
    options: OptionsImportation,
) -> list[tuple[int, str, Any]]:
    """
    Choisit les feuilles à traiter, sous la forme `(index, titre, cible)`.

    Sans déversement, une seule feuille est traitée (celle demandée par
    `options.feuille`) et `cible` vaut `None` : le fichier est conservé en
    staging, sans écriture métier.

    Avec le déversement, chaque onglet dont le titre correspond à une cible
    déclarée est traité, dans l'ordre des dépendances
    (bénéficiaires → budgets → exécutions → remboursements), de sorte que les
    références d'une feuille soient résolvables dans le même classeur.
    """
    titres = lister_feuilles(contenu, nom_fichier)

    if not options.deversement:
        index = options.feuille
        if index >= len(titres):
            raise ErreurImportation(
                f"La feuille d'index {index} n'existe pas. "
                f"Feuilles disponibles : {titres}"
            )
        return [(index, titres[index], None)]

    plan = [
        (index, titre, cible)
        for index, titre in enumerate(titres)
        if (cible := cible_pour_feuille(titre)) is not None
    ]
    if not plan:
        attendus = sorted({t for c in CIBLES for t in c.titres_feuilles})
        raise ErreurImportation(
            "Aucune feuille reconnue pour le déversement. "
            f"Onglets attendus : {', '.join(attendus)} ; "
            f"onglets trouvés : {', '.join(titres)}."
        )
    plan.sort(key=lambda entree: (entree[2].ordre, entree[0]))
    return plan


def _marquer_feuille(motifs: list[dict], index: int) -> list[dict]:
    return [{**motif, "feuille": index} for motif in motifs]


async def _traiter(
    *,
    contenu: bytes,
    nom_fichier: str,
    importation_id: ObjectId,
    options: OptionsImportation,
    digest: str,
) -> dict:
    """Phase de traitement (lecture → validation → persistance → déversement)."""
    plan = _planifier_feuilles(contenu, nom_fichier, options)

    colonnes_rapport: list[ColonneAnalysee] = []
    rejets_rapport: list[RejetImportation] = []
    feuilles_rapport: list[dict] = []
    deversements: list[dict] = []

    nb_lignes_total = 0
    nb_lignes_importees = 0
    nb_lignes_rejetees = 0
    nb_doublons = 0
    meta_fichier: dict = {}

    for index, titre, cible in plan:
        headers, grille, meta = lire_fichier(
            contenu,
            nom_fichier,
            encodage_force=options.encodage,
            delimiteur_force=options.delimiteur,
            feuille=index,
        )
        if not meta_fichier:
            meta_fichier = meta

        if not grille:
            raise ErreurImportation(
                f"La feuille « {titre} » ne contient aucune ligne de données "
                "après l'en-tête."
            )

        colonnes = analyser_colonnes(headers, grille)
        lignes_validees = valider_lignes(
            colonnes,
            grille,
            list(options.colonnes_obligatoires),
        )

        lignes_rejetees = [
            motif
            for ligne in lignes_validees
            if not ligne.valide
            for motif in ligne.erreurs
        ]

        lignes_acceptees = [l for l in lignes_validees if l.valide]
        lignes_gardees, rejets_doublons = marquer_doublons(lignes_acceptees)
        lignes_rejetees.extend(rejets_doublons)
        doublons_feuille = len(rejets_doublons)

        n_brutes = await inserer_brutes(
            importation_id, headers, grille, feuille=index
        )
        n_nettoyees = await inserer_nettoyees(
            importation_id, lignes_gardees, feuille=index
        )
        if n_brutes != len(grille):
            raise ErreurImportation(
                f"Écart de persistation des lignes brutes "
                f"({n_brutes}/{len(grille)})."
            )
        if n_nettoyees != len(lignes_gardees):
            raise ErreurImportation(
                f"Écart de persistation des lignes nettoyées "
                f"({n_nettoyees}/{len(lignes_gardees)})."
            )

        deversement = None
        rejets_deversement: list[dict] = []
        if cible is not None:
            deversement, rejets_deversement = await deverser(
                cible, lignes_gardees
            )
            deversement["feuille"] = index
            deversement["feuille_nom"] = titre
            deversements.append(deversement)
            lignes_rejetees.extend(rejets_deversement)

        lignes_rejetees = _marquer_feuille(lignes_rejetees, index)
        await inserer_rejets(importation_id, lignes_rejetees, feuille=index)

        nb_invalides_par_colonne: dict[str, int] = {}
        for motif in lignes_rejetees:
            colonne = motif["colonne"]
            if colonne == "*":
                continue
            nb_invalides_par_colonne[colonne] = (
                nb_invalides_par_colonne.get(colonne, 0) + 1
            )

        colonnes_rapport.extend(
            ColonneAnalysee(
                nom_original=c["nom_original"],
                nom_normalise=c["nom_normalise"],
                type_detecte=c["type_detecte"],
                nb_lignes=c["nb_lignes"],
                nb_vides=c["nb_vides"],
                nb_non_vides=c["nb_non_vides"],
                nb_invalides=nb_invalides_par_colonne.get(
                    c["nom_normalise"], 0
                ),
                exemples=c["exemples"],
                feuille=index,
            )
            for c in colonnes
        )
        rejets_rapport.extend(
            RejetImportation(
                ligne=m["ligne"],
                colonne=m["colonne"],
                valeur=m["valeur"],
                raison=m["raison"],
                type_erreur=m["type_erreur"],
                feuille=index,
            )
            for m in lignes_rejetees
        )

        # Une ligne retenue puis écartée au déversement est comptée deux fois
        # si on l'additionne : on la sort des « importées » pour conserver
        # total = importées + rejetées.
        importees = len(lignes_gardees) - len(rejets_deversement)
        rejetees = len(lignes_rejetees)

        nb_lignes_total += len(grille)
        nb_lignes_importees += importees
        nb_lignes_rejetees += rejetees
        nb_doublons += doublons_feuille

        feuilles_rapport.append({
            "index": index,
            "titre": titre,
            "cible": cible.cle if cible else None,
            "collection": cible.collection if cible else None,
            "nb_colonnes": len(colonnes),
            "nb_lignes_total": len(grille),
            "nb_lignes_importees": importees,
            "nb_lignes_rejetees": rejetees,
            "nb_doublons": doublons_feuille,
            "nb_deversees": (
                deversement["lignes_deversees"] if deversement else None
            ),
        })

    deversement_rapport = _synthese_deversement(deversements)

    rapport = RapportImportation(
        fichier_original=nom_fichier,
        format=meta_fichier.get("format", "xlsx"),
        taille_octets=len(contenu),
        sha256=digest,
        encodage=meta_fichier.get("encodage"),
        delimiteur=meta_fichier.get("delimiteur"),
        nb_colonnes=len(colonnes_rapport),
        nb_lignes_total=nb_lignes_total,
        nb_lignes_importees=nb_lignes_importees,
        nb_lignes_rejetees=nb_lignes_rejetees,
        nb_doublons=nb_doublons,
        colonnes=colonnes_rapport,
        rejets=rejets_rapport[:200],
        feuilles=feuilles_rapport,
        deversement=deversement_rapport,
    )

    return rapport.resume()


def _synthese_deversement(deversements: list[dict]) -> Optional[dict]:
    if not deversements:
        return None
    return {
        "active": True,
        "nb_feuilles": len(deversements),
        "insere": sum(d["insere"] for d in deversements),
        "mise_a_jour": sum(d["mise_a_jour"] for d in deversements),
        "rejetees": sum(d["rejetees"] for d in deversements),
        "collections": deversements,
    }


async def _ressource_importation(id_: ObjectId) -> dict:
    db = obtenir_database()
    doc = await db[COLLECTION_IMPORTATIONS].find_one({"_id": id_})
    if doc is None:
        from app.imports.erreurs import ErreurImportation
        raise ErreurImportation("Importation introuvable.")
    return _resume_document(doc)


def _resume_document(doc: dict[str, Any]) -> dict[str, Any]:
    rapport = doc.get("rapport") or {}
    return {
        "id": str(doc["_id"]),
        "nom_fichier": doc.get("nom_fichier"),
        "taille_octets": doc.get("taille_octets"),
        "sha256": doc.get("sha256"),
        "type_mime": doc.get("type_mime"),
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


def _extension(nom_fichier: str) -> str:
    return Path(nom_fichier).suffix.lower()