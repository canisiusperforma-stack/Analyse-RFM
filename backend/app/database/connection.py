from typing import Optional

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.config import settings
from app.database.client import creer_client
from app.database.errors import ErreurConnexionDatabase
from app.utils.logging import get_logger

logger = get_logger(__name__)

_client: Optional[AsyncIOMotorClient] = None
_database: Optional[AsyncIOMotorDatabase] = None


def obtenir_client() -> AsyncIOMotorClient:
    if _client is None:
        raise ErreurConnexionDatabase(
            "Aucune connexion MongoDB : appeler connecter_database() au préalable"
        )
    return _client


def obtenir_database() -> AsyncIOMotorDatabase:
    if _database is None:
        raise ErreurConnexionDatabase(
            "Aucune base de données MongoDB : appeler connecter_database() au préalable"
        )
    return _database


def etat_base_donnees() -> dict:
    """Renvoie l'état courant de la connexion MongoDB."""
    return {
        "url": settings.MONGODB_URL,
        "base": settings.MONGODB_DATABASE,
        "connecte": _client is not None,
    }


async def connecter_database() -> AsyncIOMotorDatabase:
    """Connexion asynchrone à MongoDB (idempotente)."""
    global _client, _database

    if _client is not None and _database is not None:
        return _database

    client = None
    try:
        client = creer_client()
        await client.admin.command("ping")
        _client = client
        _database = client[settings.MONGODB_DATABASE]
        logger.info(
            "Connexion MongoDB établie sur la base '%s'",
            settings.MONGODB_DATABASE,
        )
        return _database
    except Exception as erreur:
        if client is not None:
            client.close()
        logger.error("Connexion MongoDB impossible : %s", erreur)
        raise ErreurConnexionDatabase(
            f"Impossible de se connecter à MongoDB : {erreur}"
        ) from erreur


async def fermer_database() -> None:
    """Fermeture propre et idempotente de la connexion MongoDB."""
    global _client, _database

    client = _client
    _client = None
    _database = None

    if client is not None:
        client.close()
        logger.info("Connexion MongoDB fermée")
    else:
        logger.info("Aucune connexion MongoDB active à fermer")