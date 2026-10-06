"""Persistance des importations : métadonnées, brut, nettoyé, rejets, fichier."""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Optional

from bson import Decimal128, ObjectId
from motor.motor_asyncio import AsyncIOMotorGridFSBucket
from pymongo import ASCENDING, DESCENDING

from app.database import obtenir_database

COLLECTION_IMPORTATIONS = "importations"
COLLECTION_BRUTES = "importations_brutes"
COLLECTION_NETTOYEES = "importations_nettoyees"
COLLECTION_REJETS = "importations_rejets"

BUCKET_FICHIERS = "imports"

TAILLE_SOUS_RAPPORT_REJETS = 200


def bsoniser_valeurs(valeurs: dict[str, Any]) -> dict[str, Any]:
    """Convertit Decimal/date en types BSON sûrs pour MongoDB."""
    resultat: dict[str, Any] = {}
    for cle, valeur in valeurs.items():
        if isinstance(valeur, Decimal):
            resultat[cle] = Decimal128(valeur)
        elif isinstance(valeur, date) and not isinstance(valeur, datetime):
            resultat[cle] = datetime(
                valeur.year, valeur.month, valeur.day, tzinfo=timezone.utc
            )
        elif isinstance(valeur, datetime) and valeur.tzinfo is None:
            resultat[cle] = valeur.replace(tzinfo=timezone.utc)
        else:
            resultat[cle] = valeur
    return resultat


async def assurer_indexes() -> None:
    """Crée (idempotent) les index des collections d'importation."""
    db = obtenir_database()

    await db[COLLECTION_IMPORTATIONS].create_index(
        [("importe_le", DESCENDING)]
    )
    await db[COLLECTION_IMPORTATIONS].create_index([("statut", ASCENDING)])

    # Le numéro de ligne n'est unique que par feuille : un classeur en import
    # plusieurs feuilles à la fois. L'ancien index (sans `feuille`) serait
    # levé au profit du nouveau.
    for collection in (COLLECTION_BRUTES, COLLECTION_NETTOYEES):
        try:
            await db[collection].drop_index("importation_id_1_ligne_1")
        except Exception:  # noqa: BLE001
            pass
        await db[collection].create_index(
            [("importation_id", ASCENDING), ("feuille", ASCENDING),
             ("ligne", ASCENDING)],
            unique=True,
        )

    await db[COLLECTION_REJETS].create_index(
        [("importation_id", ASCENDING), ("feuille", ASCENDING),
         ("ligne", ASCENDING), ("colonne", ASCENDING)]
    )
    await db[COLLECTION_REJETS].create_index(
        [("importation_id", ASCENDING), ("type_erreur", ASCENDING)]
    )


def _bucket() -> AsyncIOMotorGridFSBucket:
    return AsyncIOMotorGridFSBucket(obtenir_database(), bucket_name=BUCKET_FICHIERS)


async def sauvegarder_fichier_original(
    contenu: bytes,
    nom_fichier: str,
    type_mime: str,
    sha256: str,
) -> ObjectId:
    """Stocke le fichier d'origine (jamais modifié) dans GridFS."""
    bucket = _bucket()
    file_id = await bucket.upload_from_stream(
        nom_fichier,
        contenu,
        metadata={"sha256": sha256, "type_mime": type_mime, "original": True},
    )
    return file_id


async def lire_fichier_original(file_id: ObjectId) -> bytes:
    bucket = _bucket()
    try:
        stream = await bucket.open_download_stream(file_id)
        return await stream.read()
    except Exception:
        raise


async def inserer_importation(
    importation_id: ObjectId,
    document: dict[str, Any],
) -> None:
    db = obtenir_database()
    await db[COLLECTION_IMPORTATIONS].update_one(
        {"_id": importation_id},
        {"$set": document},
        upsert=True,
    )


async def finaliser_importation(
    importation_id: ObjectId,
    statut: str,
    rapport: Optional[dict] = None,
    erreur: Optional[str] = None,
) -> None:
    db = obtenir_database()
    mise_a_jour: dict[str, Any] = {"statut": statut}
    if rapport is not None:
        mise_a_jour["rapport"] = rapport
    if erreur:
        mise_a_jour["erreur"] = erreur
    await db[COLLECTION_IMPORTATIONS].update_one(
        {"_id": importation_id},
        {"$set": mise_a_jour},
    )


async def inserer_brutes(
    importation_id: ObjectId,
    colonnes_originales: list[str],
    grille: list[list[Any]],
    feuille: int = 0,
) -> int:
    db = obtenir_database()
    docs = []
    for index_ligne, row in enumerate(grille, start=1):
        valeurs = {
            nom: brute
            for nom, brute in zip(colonnes_originales, row)
            if nom != ""
        }
        docs.append({
            "importation_id": importation_id,
            "feuille": feuille,
            "ligne": index_ligne,
            "valeurs": valeurs,
        })
    if not docs:
        return 0

    for i in range(0, len(docs), 500):
        await db[COLLECTION_BRUTES].insert_many(docs[i : i + 500])
    return len(docs)


async def inserer_nettoyees(
    importation_id: ObjectId,
    lignes_validees: list,
    feuille: int = 0,
) -> int:
    db = obtenir_database()
    docs = []
    for lv in lignes_validees:
        docs.append({
            "importation_id": importation_id,
            "feuille": feuille,
            "ligne": lv.numero,
            "valeurs": bsoniser_valeurs(lv.valeurs),
            "manquantes": lv.manquantes,
        })
    if not docs:
        return 0

    for i in range(0, len(docs), 500):
        await db[COLLECTION_NETTOYEES].insert_many(docs[i : i + 500])
    return len(docs)


async def inserer_rejets(
    importation_id: ObjectId,
    rejets: list[dict],
    feuille: int = 0,
) -> int:
    db = obtenir_database()
    if not rejets:
        return 0

    docs = [
        {"importation_id": importation_id, "feuille": feuille, **motif}
        for motif in rejets
    ]
    for i in range(0, len(docs), 500):
        await db[COLLECTION_REJETS].insert_many(docs[i : i + 500])
    return len(docs)


async def recuperer_importation(importation_id: ObjectId) -> Optional[dict]:
    db = obtenir_database()
    return await db[COLLECTION_IMPORTATIONS].find_one({"_id": importation_id})


async def lister_importations(
    limite: int = 50,
    saut: int = 0,
) -> list[dict]:
    db = obtenir_database()
    curseur = (
        db[COLLECTION_IMPORTATIONS]
        .find({}, {"rapport": 0})
        .sort("importe_le", DESCENDING)
        .skip(max(saut, 0))
        .limit(min(max(limite, 1), 500))
    )
    return [doc async for doc in curseur]


async def lister_rejets(
    importation_id: ObjectId,
    limite: int = 200,
    saut: int = 0,
) -> list[dict]:
    db = obtenir_database()
    curseur = (
        db[COLLECTION_REJETS]
        .find({"importation_id": importation_id})
        .sort([("feuille", ASCENDING), ("ligne", ASCENDING),
               ("colonne", ASCENDING)])
        .skip(max(saut, 0))
        .limit(min(max(limite, 1), 1000))
    )
    return [doc async for doc in curseur]


async def lister_brutes(
    importation_id: ObjectId,
    limite: int = 200,
    saut: int = 0,
) -> list[dict]:
    """Renvoie les lignes brutes conservées (jamais modifiées)."""
    db = obtenir_database()
    curseur = (
        db[COLLECTION_BRUTES]
        .find({"importation_id": importation_id})
        .sort([("feuille", ASCENDING), ("ligne", ASCENDING)])
        .skip(max(saut, 0))
        .limit(min(max(limite, 1), 1000))
    )
    return [doc async for doc in curseur]


async def lister_nettoyees(
    importation_id: ObjectId,
    limite: int = 200,
    saut: int = 0,
) -> list[dict]:
    """Renvoie les lignes nettoyées conservées (normes appliquées)."""
    db = obtenir_database()
    curseur = (
        db[COLLECTION_NETTOYEES]
        .find({"importation_id": importation_id})
        .sort([("feuille", ASCENDING), ("ligne", ASCENDING)])
        .skip(max(saut, 0))
        .limit(min(max(limite, 1), 1000))
    )
    return [doc async for doc in curseur]


async def attendre_ecritures() -> None:
    await asyncio.sleep(0)