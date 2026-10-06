"""Accès aux données de la collection `utilisateurs`."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from bson import ObjectId
from pymongo import ASCENDING

from app.database import obtenir_database

COLLECTION_UTILISATEURS = "utilisateurs"


async def assurer_indexes() -> None:
    """Crée (idempotent) les index de la collection des utilisateurs."""
    db = obtenir_database()
    await db[COLLECTION_UTILISATEURS].create_index("email", unique=True)
    await db[COLLECTION_UTILISATEURS].create_index(
        [("actif", ASCENDING), ("role", ASCENDING)]
    )


async def trouver_par_email(email: str) -> Optional[dict]:
    """Recherche un utilisateur par e-mail normalisé."""
    db = obtenir_database()
    return await db[COLLECTION_UTILISATEURS].find_one({"email": email})


async def trouver_par_id(identifiant: Any) -> Optional[dict]:
    """Recherche un utilisateur par identifiant ObjectId."""
    try:
        oid = ObjectId(identifiant)
    except Exception:
        return None
    db = obtenir_database()
    return await db[COLLECTION_UTILISATEURS].find_one({"_id": oid})


async def creer(utilisateur: dict) -> ObjectId:
    """Insère un utilisateur et renvoie son identifiant."""
    db = obtenir_database()
    resultat = await db[COLLECTION_UTILISATEURS].insert_one(utilisateur)
    return resultat.inserted_id


async def mettre_a_jour_derniere_connexion(
    identifiant: ObjectId,
    quand: Optional[datetime] = None,
) -> None:
    """Enregistre la dernière connexion réussie de l'utilisateur."""
    db = obtenir_database()
    maintenant = quand or datetime.now(timezone.utc)
    await db[COLLECTION_UTILISATEURS].update_one(
        {"_id": identifiant},
        {
            "$set": {
                "derniere_connexion": maintenant,
                "updated_at": maintenant,
            }
        },
    )


async def lister(
    limite: int = 50,
    saut: int = 0,
    role: Optional[str] = None,
    actif: Optional[bool] = None,
) -> list[dict]:
    """Liste les utilisateurs (filtres optionnels par rôle et activité)."""
    db = obtenir_database()
    filtres: dict = {}
    if role:
        filtres["role"] = role
    if actif is not None:
        filtres["actif"] = actif
    curseur = (
        db[COLLECTION_UTILISATEURS]
        .find(filtres)
        .sort("created_at", -1)
        .skip(saut)
        .limit(limite)
    )
    return [document for document in await curseur.to_list(length=limite)]


async def compter(role: Optional[str] = None, actif: Optional[bool] = None) -> int:
    """Compte les utilisateurs selon les mêmes filtres que `lister`."""
    db = obtenir_database()
    filtres: dict = {}
    if role:
        filtres["role"] = role
    if actif is not None:
        filtres["actif"] = actif
    return await db[COLLECTION_UTILISATEURS].count_documents(filtres)


async def mettre_a_jour(
    identifiant: ObjectId,
    donnees: dict,
) -> Optional[dict]:
    """Met à jour sélectivement un utilisateur et renvoie le document à jour."""
    db = obtenir_database()
    if donnees:
        donnees["updated_at"] = datetime.now(timezone.utc)
        await db[COLLECTION_UTILISATEURS].update_one(
            {"_id": identifiant},
            {"$set": donnees},
        )
    return await trouver_par_id(identifiant)


async def supprimer(identifiant: ObjectId) -> bool:
    """Supprime définitivement un utilisateur (admin uniquement)."""
    db = obtenir_database()
    resultat = await db[COLLECTION_UTILISATEURS].delete_one(
        {"_id": identifiant}
    )
    return resultat.deleted_count > 0