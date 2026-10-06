"""Persistance de la base documentaire : documents et morceaux indexés.

Deux collections, conformément à `docs/modele-donnees.md` qui prévoit l'entité
`documents` (contenu dans GridFS) comme source du RAG :

- `documents`       — métadonnées, classification, droits d'accès, état ;
- `documents_morceaux` — un document par fragment, avec son vecteur et une
  **copie de la classification**. Cette redondance est délibérée : le filtrage
  d'accès est évalué sur les morceaux, dans la requête, et non sur le document
  parent. Un morceau porte donc les mêmes droits que son document, ce qui évite
  une jointure à chaque recherche et, surtout, garantit qu'une évolution du
  filtrage ne puisse pas laisser un morceau orphelin lisible par défaut.
  `synchroniser_acces_document` répercute toute modification de classification
  sur les morceaux existants.

Les accès en lecture des morceaux passent **exclusivement** par `vector_store`,
qui applique `app.models.document.filtre_acces_documents`. Aucune fonction de ce
module n'est un point d'entrée de lecture non filtrée.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional, Sequence

from bson import ObjectId
from pymongo import ASCENDING, DESCENDING

from app.database import obtenir_database
from app.models.document import (
    STATUT_ECHEC,
    STATUT_EN_ATTENTE,
    STATUT_INDEXE,
    normaliser_niveau,
)

COLLECTION_DOCUMENTS = "documents"
COLLECTION_MORCEAUX = "documents_morceaux"

BUCKET_DOCUMENTS = "documents"

#: Champs projetés lors d'une recherche : ni le vecteur ni le texte brut n'ont
#: d'intérêt dans une liste, et le vectur[$] d'un morceau ferait exploser la
#: réponse HTTP.
PROJECTION_LEGERE = {"vecteur": 0, "contenu": 0}


async def assurer_indexes() -> None:
    """Crée (idempotent) les index de la base documentaire."""
    db = obtenir_database()

    await db[COLLECTION_DOCUMENTS].create_index([("nom_fichier", ASCENDING)])
    await db[COLLECTION_DOCUMENTS].create_index(
        [("statut_indexation", ASCENDING)]
    )
    await db[COLLECTION_DOCUMENTS].create_index(
        [("created_at", DESCENDING)]
    )
    await db[COLLECTION_DOCUMENTS].create_index([("confidentialite", ASCENDING)])

    await db[COLLECTION_MORCEAUX].create_index(
        [("document_id", ASCENDING), ("ordinal", ASCENDING)],
        unique=True,
    )
    await db[COLLECTION_MORCEAUX].create_index(
        [("document_id", ASCENDING)]
    )
    # Index d'accès : les deux premiers termes de la clause `$or` construite par
    # `filtre_acces_documents`, pour que le tri des candidats serve le filtrage
    # plutôt que de le subir.
    await db[COLLECTION_MORCEAUX].create_index(
        [("confidentialite", ASCENDING), ("roles_autorises", ASCENDING)]
    )
    await db[COLLECTION_MORCEAUX].create_index(
        [("contenu", "text"), ("titre", "text")],
        default_language="none",
    )


# --- Documents -------------------------------------------------------------


async def inserer_document(document: dict[str, Any]) -> ObjectId:
    """Insère les métadonnées d'un document et renvoie son identifiant."""
    db = obtenir_database()
    resultat = await db[COLLECTION_DOCUMENTS].insert_one(document)
    return resultat.inserted_id


async def recuperer_document(identifiant: ObjectId) -> Optional[dict]:
    db = obtenir_database()
    return await db[COLLECTION_DOCUMENTS].find_one({"_id": identifiant})


async def recuperer_document_accessible(
    identifiant: ObjectId,
    filtre: dict[str, Any],
) -> Optional[dict]:
    """Récupère un document **à travers une clause d'accès**.

    Le filtre d'accès est appliqué dans la requête, jamais après : un document
    interdit n'est donc jamais chargé, et ne peut pas l'être par erreur de
    projection ou de traitement ultérieur. Renvoie `None` — que l'appelant
    traduit par `404` — pour un identifiant inconnu comme pour un document
    qu'on n'a pas le droit de voir, afin que les deux cas restent
    indiscernables.
    """
    db = obtenir_database()
    return await db[COLLECTION_DOCUMENTS].find_one({"_id": identifiant, **filtre})


async def lister_documents(
    filtre: Optional[dict] = None,
    limite: int = 50,
    saut: int = 0,
) -> list[dict]:
    """Liste les documents autorisés (le filtre d'accès est fourni par l'appelant)."""
    db = obtenir_database()
    curseur = (
        db[COLLECTION_DOCUMENTS]
        .find(filtre or {}, PROJECTION_LEGERE)
        .sort("created_at", DESCENDING)
        .skip(max(saut, 0))
        .limit(min(max(limite, 1), 500))
    )
    return [document async for document in curseur]


async def compter_documents(filtre: Optional[dict] = None) -> int:
    db = obtenir_database()
    return await db[COLLECTION_DOCUMENTS].count_documents(filtre or {})


async def supprimer_document(identifiant: ObjectId) -> bool:
    """Supprime un document, ses morceaux indexés et son fichier d'origine."""
    db = obtenir_database()

    await db[COLLECTION_MORCEAUX].delete_many({"document_id": identifiant})

    document = await db[COLLECTION_DOCUMENTS].find_one({"_id": identifiant})
    if document is not None and document.get("file_id") is not None:
        try:
            from motor.motor_asyncio import AsyncIOMotorGridFSBucket

            bucket = AsyncIOMotorGridFSBucket(
                db, bucket_name=BUCKET_DOCUMENTS
            )
            await bucket.delete(document["file_id"])
        except Exception:  # noqa: BLE001
            # Le fichier d'origine peut déjà avoir disparu : la suppression des
            # métadonnées et des morceaux doit aboutir malgré tout, faute de
            # quoi un document resterait indexable sans être supprimable.
            from app.utils.logging import get_logger

            get_logger(__name__).warning(
                "Fichier GridFS %s introuvable lors de la suppression du document %s",
                document.get("file_id"),
                identifiant,
            )

    resultat = await db[COLLECTION_DOCUMENTS].delete_one({"_id": identifiant})
    return resultat.deleted_count > 0


async def enregistrer_etat_indexation(
    identifiant: ObjectId,
    statut: str,
    nb_morceaux: int = 0,
    erreur: Optional[str] = None,
    metadonnees: Optional[dict[str, Any]] = None,
) -> None:
    """Met à jour l'issue de l'indexation (étape du pipeline, pas du modèle)."""
    db = obtenir_database()
    maintenant = datetime.now(timezone.utc)
    mise_a_jour: dict[str, Any] = {
        "statut_indexation": statut,
        "nb_morceaux": max(nb_morceaux, 0),
        "indexe_le": maintenant if statut == STATUT_INDEXE else None,
        "erreur_indexation": erreur,
        "updated_at": maintenant,
    }
    if metadonnees:
        mise_a_jour.update(metadonnees)
    await db[COLLECTION_DOCUMENTS].update_one(
        {"_id": identifiant}, {"$set": mise_a_jour}
    )


async def modifier_document(
    identifiant: ObjectId,
    donnees: dict[str, Any],
) -> Optional[dict]:
    """Met à jour les métadonnées d'un document et renvoie son état à jour."""
    db = obtenir_database()
    if donnees:
        donnees["updated_at"] = datetime.now(timezone.utc)
        await db[COLLECTION_DOCUMENTS].update_one(
            {"_id": identifiant}, {"$set": donnees}
        )
    return await recuperer_document(identifiant)


# --- Fichier d'origine -----------------------------------------------------


async def sauvegarder_fichier(contenu: bytes, nom_fichier: str, type_mime: str) -> ObjectId:
    """Stocke le fichier d'origine dans GridFS, sans jamais le modifier."""
    from motor.motor_asyncio import AsyncIOMotorGridFSBucket

    bucket = AsyncIOMotorGridFSBucket(obtenir_database(), bucket_name=BUCKET_DOCUMENTS)
    return await bucket.upload_from_stream(
        nom_fichier,
        contenu,
        metadata={"type_mime": type_mime, "original": True},
    )


async def lire_fichier(file_id: ObjectId) -> bytes:
    from motor.motor_asyncio import AsyncIOMotorGridFSBucket

    bucket = AsyncIOMotorGridFSBucket(obtenir_database(), bucket_name=BUCKET_DOCUMENTS)
    flux = await bucket.open_download_stream(file_id)
    return await flux.read()


async def supprimer_fichier(file_id: ObjectId) -> bool:
    """Supprime un fichier archivé dans GridFS.

    Isolé de `supprimer_document` pour être appelable en dépannage : si
    l'insertion des métadonnées échoue après l'archivage, le fichier doit
    pouvoir être retiré, faute de quoi il resterait orphelin — invisible dans
    la liste, donc impossible à supprimer par l'interface.
    """
    from motor.motor_asyncio import AsyncIOMotorGridFSBucket

    bucket = AsyncIOMotorGridFSBucket(obtenir_database(), bucket_name=BUCKET_DOCUMENTS)
    await bucket.delete(file_id)
    return True


# --- Morceaux indexés ------------------------------------------------------


def _morceau_bson(
    document_id: ObjectId,
    document: dict[str, Any],
    morceau: Any,
    vecteur: Sequence[float],
) -> dict[str, Any]:
    """Construit le document BSON d'un morceau, classification comprise.

    La classification est recopiée depuis le document à chaque indexation. Le
    morceau est ainsi autonome du point de vue des droits, et une recherche ne
    peut pas aboutir à contourner l'accès au document parent.
    """
    return {
        "document_id": document_id,
        "ordinal": morceau.ordinal,
        "contenu": morceau.texte,
        "titre": morceau.titre,
        "page": morceau.page,
        "debut_source": morceau.debut_source,
        "fin_source": morceau.fin_source,
        "nb_caracteres": morceau.nb_caracteres,
        "vecteur": [float(valeur) for valeur in vecteur],
        "confidentialite": normaliser_niveau(document.get("confidentialite")),
        "roles_autorises": document.get("roles_autorises") or [],
        "utilisateurs_autorises": [
            str(identifiant)
            for identifiant in (document.get("utilisateurs_autorises") or [])
        ],
        # Nom et type sont recopiés afin que la recherche n'exige qu'une seule
        # requête. Le document n'étant pas renommable par l'API, ces deux
        # valeurs ne peuvent pas diverger de leur source.
        "nom_fichier": document.get("nom_fichier"),
        "type_mime": document.get("type_mime"),
        "created_at": datetime.now(timezone.utc),
    }


async def remplacer_morceaux(
    document_id: ObjectId,
    document: dict[str, Any],
    morceaux: list[Any],
    vecteurs: list[Sequence[float]],
) -> int:
    """Remplace l'ensemble des morceaux d'un document (réindexation idempotente)."""
    db = obtenir_database()
    await db[COLLECTION_MORCEAUX].delete_many({"document_id": document_id})

    if not morceaux:
        return 0

    documents = [
        _morceau_bson(document_id, document, morceau, vecteur)
        for morceau, vecteur in zip(morceaux, vecteurs)
    ]
    for debut in range(0, len(documents), 200):
        await db[COLLECTION_MORCEAUX].insert_many(documents[debut : debut + 200])
    return len(documents)


async def supprimer_morceaux(document_id: ObjectId) -> int:
    db = obtenir_database()
    resultat = await db[COLLECTION_MORCEAUX].delete_many({"document_id": document_id})
    return resultat.deleted_count


async def compter_morceaux(filtre: Optional[dict] = None) -> int:
    db = obtenir_database()
    return await db[COLLECTION_MORCEAUX].count_documents(filtre or {})


async def synchroniser_acces_document(document_id: ObjectId) -> int:
    """Recopie la classification du document sur ses morceaux déjà indexés.

    Appelé après toute modification de classification ou de liste d'autorisés.
    Sans cela, un document promu de `interne` à `confidentielle` continuerait de
    répondre par des morceaux portant encore l'ancienne classification.
    """
    db = obtenir_database()
    document = await db[COLLECTION_DOCUMENTS].find_one({"_id": document_id})
    if document is None:
        return 0

    resultat = await db[COLLECTION_MORCEAUX].update_many(
        {"document_id": document_id},
        {
            "$set": {
                "confidentialite": normaliser_niveau(
                    document.get("confidentialite")
                ),
                "roles_autorises": document.get("roles_autorises") or [],
                "utilisateurs_autorises": [
                    str(identifiant)
                    for identifiant in (document.get("utilisateurs_autorises") or [])
                ],
            }
        },
    )
    return resultat.modified_count


async def statistiques_base() -> dict[str, Any]:
    """Volume de la base documentaire, pour la route de diagnostic."""
    db = obtenir_database()
    total = await db[COLLECTION_DOCUMENTS].count_documents({})
    par_statut: dict[str, int] = {}
    curseur = db[COLLECTION_DOCUMENTS].aggregate([
        {"$group": {"_id": "$statut_indexation", "total": {"$sum": 1}}},
    ])
    async for ligne in curseur:
        par_statut[str(ligne.get("_id") or "inconnu")] = int(ligne.get("total", 0))

    return {
        "documents": total,
        "morceaux": await db[COLLECTION_MORCEAUX].count_documents({}),
        "par_statut": par_statut,
        "en_attente": par_statut.get(STATUT_EN_ATTENTE, 0),
        "echecs": par_statut.get(STATUT_ECHEC, 0),
    }
