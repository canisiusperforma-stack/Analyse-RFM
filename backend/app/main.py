from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import router as api_router
from app.config import settings
from app.database import connecter_database, fermer_database
from app.repositories import document_repository
from app.utils.errors import enregistrer_gestionnaires_erreurs
from app.utils.logging import configurer_logging, get_logger

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    configurer_logging()
    logger.info(
        "%s démarrée (environnement : %s, version : %s)",
        settings.APP_NAME,
        settings.APP_ENV,
        settings.APP_VERSION,
    )
    try:
        await connecter_database()
    except Exception as erreur:
        logger.error(
            "Démarrage en mode dégradé : connexion MongoDB impossible (%s)",
            erreur,
        )
    else:
        # Les index de la base documentaire conditionnent la barrière de
        # sécurité du RAG autant que sa performance : l'index composé
        # `(confidentialite, roles_autorises)` est celui qui permet au tri des
        # candidats de servir le filtrage d'accès au lieu de le subir. Sans lui,
        # chaque recherche parcourt tous les extraits — le confidentialiel
        # compris — pour n'en garder qu'une fraction. Leur création est
        # idempotente ; un échec est journalisé sans interrompre le démarrage,
        # la base restant fonctionnelle, seulement plus lentement.
        if settings.RAG_ENABLED:
            try:
                await document_repository.assurer_indexes()
                logger.info("Index de la base documentaire vérifiés.")
            except Exception as erreur:  # noqa: BLE001
                logger.error(
                    "Création des index documentaires impossible (%s) : la "
                    "recherche documentaire sera plus lente.",
                    erreur,
                )
        else:
            logger.info(
                "Recherche documentaire désactivée (RAG_ENABLED=false) : "
                "aucun index documentaire n'est créé."
            )
    yield
    await fermer_database()
    logger.info("%s arrêtée", settings.APP_NAME)


app = FastAPI(
    title=settings.APP_NAME,
    description=settings.APP_DESCRIPTION,
    version=settings.APP_VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
    contact={
        "name": "RFM SRB Vatovavy",
    },
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
    allow_methods=settings.cors_allow_methods,
    allow_headers=settings.cors_allow_headers,
)

enregistrer_gestionnaires_erreurs(app)

app.include_router(api_router, prefix="/api")


@app.get(
    "/",
    summary="Informations sur l'API",
    description=(
        "Point d'entrée de l'API : renvoie les informations générales "
        "et les liens vers la documentation."
    ),
    tags=["Système"],
)
async def accueil() -> dict:
    return {
        "nom": settings.APP_NAME,
        "description": settings.APP_DESCRIPTION,
        "version": settings.APP_VERSION,
        "environnement": settings.APP_ENV,
        "documentation": {
            "swagger": "/docs",
            "redoc": "/redoc",
            "openapi": "/openapi.json",
        },
        "sante": "/api/sante",
    }