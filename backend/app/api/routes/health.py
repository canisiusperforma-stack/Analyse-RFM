from datetime import datetime, timezone

from fastapi import APIRouter

from app.config import settings
from app.database import verifier_connexion_mongodb
from app.utils.logging import get_logger

router = APIRouter()

logger = get_logger(__name__)


@router.get(
    "/sante",
    summary="Vérification de l'état de l'API",
    description=(
        "Endpoint de santé : vérifie que l'API répond et que la connexion "
        "à MongoDB est opérationnelle."
    ),
)
async def verification_sante() -> dict:
    mongo_ok = False
    mongo_detail = None

    try:
        await verifier_connexion_mongodb()
        mongo_ok = True
    except Exception as erreur:
        mongo_detail = str(erreur)
        logger.warning("MongoDB injoignable : %s", erreur)

    if mongo_ok:
        logger.info("Vérification de santé OK")
        return {
            "statut": "ok",
            "api": "ok",
            "mongodb": "ok",
            "version": settings.APP_VERSION,
            "environnement": settings.APP_ENV,
            "horodatage": datetime.now(timezone.utc).isoformat(),
        }

    return {
        "statut": "degrade",
        "api": "ok",
        "mongodb": "erreur",
        "detail": mongo_detail,
        "version": settings.APP_VERSION,
        "environnement": settings.APP_ENV,
        "horodatage": datetime.now(timezone.utc).isoformat(),
    }