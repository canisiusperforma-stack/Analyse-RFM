from motor.motor_asyncio import AsyncIOMotorClient

from app.config import settings

DELAI_SELECTION_MAX_MS = 5000
DELAI_CONNEXION_MAX_MS = 5000
TAILLE_POOL_MAX = 50
TAILLE_POOL_MIN = 1


def creer_client() -> AsyncIOMotorClient:
    """Crée un client MongoDB asynchrone avec des réglages d'échec rapide."""
    return AsyncIOMotorClient(
        settings.MONGODB_URL,
        serverSelectionTimeoutMS=DELAI_SELECTION_MAX_MS,
        connectTimeoutMS=DELAI_CONNEXION_MAX_MS,
        maxPoolSize=TAILLE_POOL_MAX,
        minPoolSize=TAILLE_POOL_MIN,
        tz_aware=True,
        uuidRepresentation="standard",
    )