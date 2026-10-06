from fastapi import APIRouter

from app.api.routes import (
    analyses,
    anomalies,
    assistant,
    auth,
    beneficiaires,
    budgets,
    dashboard,
    documents,
    health,
    imports,
    previsions,
    rapports,
    remboursements,
    simulations,
    utilisateurs,
)

router = APIRouter()

# Le chemin `/sante` est déclaré dans `health.py` et non ajouté ici comme
# préfixe : les deux produisaient `/api/sante/sante`, alors que l'URL
# d'accueilance annoncée par `app.main` est `/api/sante`.
router.include_router(health.router, tags=["Santé"])

v1 = APIRouter()

v1.include_router(auth.router, prefix="/auth", tags=["Authentification"])
v1.include_router(
    beneficiaires.router,
    prefix="/beneficiaires",
    tags=["Bénéficiaires"],
)
v1.include_router(budgets.router, prefix="/budgets", tags=["Budgets"])
v1.include_router(
    dashboard.router,
    prefix="/dashboard",
    tags=["Tableau de bord"],
)
v1.include_router(
    simulations.router,
    prefix="/simulations",
    tags=["Simulations"],
)
v1.include_router(
    remboursements.router,
    prefix="/remboursements",
    tags=["Remboursements"],
)
v1.include_router(analyses.router, prefix="/analyses", tags=["Analyses"])
v1.include_router(anomalies.router, prefix="/anomalies", tags=["Anomalies"])
v1.include_router(previsions.router, prefix="/previsions", tags=["Prévisions"])
v1.include_router(rapports.router, prefix="/rapports", tags=["Rapports"])
v1.include_router(documents.router, prefix="/documents", tags=["Documents"])
v1.include_router(assistant.router, prefix="/assistant", tags=["Assistant"])
v1.include_router(
    imports.router,
    prefix="/imports",
    tags=["Importation de données"],
)
v1.include_router(
    utilisateurs.router,
    prefix="/utilisateurs",
    tags=["Utilisateurs"],
)

router.include_router(v1, prefix="/v1")