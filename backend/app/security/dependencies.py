"""Dépendances FastAPI d'authentification (récupération de l'utilisateur)."""

from __future__ import annotations

from typing import Optional

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.security.jwt import decoder_jeton
from app.services.auth_service import obtenir_utilisateur_connecte
from app.utils.errors import ErreurUnauthorized

_authentification_bearer = HTTPBearer(auto_error=False)

MESSAGE_AUTH_REQUISE = (
    "Authentification requise : en-tête 'Authorization: Bearer <jeton>'."
)


async def obtenir_utilisateur_actuel(
    identifiants: Optional[
        HTTPAuthorizationCredentials
    ] = Depends(_authentification_bearer),
) -> dict:
    """
    Dépendance FastAPI : vérifie le jeton JWT de la requête et renvoie
    l'utilisateur courant (document `utilisateurs`).

    Le jeton doit être valide (signature, expiration, émetteur) et
    l'utilisateur doit exister et être actif.
    """
    if identifiants is None or not identifiants.credentials:
        raise ErreurUnauthorized(MESSAGE_AUTH_REQUISE)

    charge = decoder_jeton(identifiants.credentials)
    return await obtenir_utilisateur_connecte(charge.get("sub"))