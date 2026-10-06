"""Routes d'authentification : inscription, connexion, utilisateur courant."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.models.utilisateur import champs_publics
from app.schemas.auth import ConnexionSchema, CreationCompteSchema
from app.security.dependencies import obtenir_utilisateur_actuel
from app.services.auth_service import connecter, creer_compte
from app.services.permission_service import permissions_utilisateur

router = APIRouter()


@router.post(
    "/inscription",
    status_code=201,
    summary="Créer un compte",
    description=(
        "Crée un compte utilisateur. Le mot de passe est hashé (bcrypt), "
        "jamais stocké ni renvoyé en clair. Renvoie un jeton d'accès et "
        "l'utilisateur créé."
    ),
)
async def inscription(donnees: CreationCompteSchema):
    return await creer_compte(
        prenom=donnees.prenom,
        nom=donnees.nom,
        email=donnees.email,
        mot_de_passe=donnees.mot_de_passe,
        role=donnees.role,
    )


@router.post(
    "/connexion",
    summary="Se connecter",
    description=(
        "Vérifie les identifiants et renvoie un jeton d'accès (JWT) avec "
        "sa date d'expiration et l'utilisateur connecté."
    ),
)
async def connexion(donnees: ConnexionSchema):
    return await connecter(
        email=donnees.email,
        mot_de_passe=donnees.mot_de_passe,
    )


@router.get(
    "/me",
    summary="Utilisateur connecté",
    description=(
        "Renvoie l'utilisateur courant. Vérifie la validité du jeton "
        "Bearer (signature, expiration) et l'état actif du compte."
    ),
)
async def utilisateur_courant(
    utilisateur: dict = Depends(obtenir_utilisateur_actuel),
):
    return {
        "utilisateur": champs_publics(utilisateur),
        "permissions": permissions_utilisateur(utilisateur),
    }