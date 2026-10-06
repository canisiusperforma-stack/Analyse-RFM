"""Dépendances FastAPI de contrôle d'accès (RBAC).

Le backend reste l'autorité : chaque route déclare la permission
requise via `Depends(exiger_permission("module:action"))`. En cas de
permission manquante, une réponse 403 `ErreurForbidden` est renvoyée.
"""

from __future__ import annotations

from fastapi import Depends

from app.security.dependencies import obtenir_utilisateur_actuel
from app.services.permission_service import (
    module_accessible,
    role_valide,
    verifier_permission,
)
from app.utils.errors import ErreurForbidden


def exiger_permission(permission: str):
    """
    Fabrique une dépendance FastAPI qui exige une permission granulaire.

    Usage : `Utilisateur = Depends(exiger_permission("rapports:generer"))`.
    Le jeton est vérifié puis la permission est contrôlée (403 si absente).
    """

    async def _verifier(
        utilisateur: dict = Depends(obtenir_utilisateur_actuel),
    ) -> dict:
        verifier_permission(utilisateur, permission)
        return utilisateur

    return _verifier


def exiger_module(module: str):
    """
    Fabrique une dépendance FastAPI qui exige un accès (quel qu'il soit)
    au module.

    Usage : `Utilisateur = Depends(exiger_module("utilisateurs"))`.
    Le contrôle granulaire par action passe par `exiger_permission`.
    """

    async def _verifier(
        utilisateur: dict = Depends(obtenir_utilisateur_actuel),
    ) -> dict:
        if not module_accessible(utilisateur, module):
            raise ErreurForbidden(
                f"Accès refusé : module '{module}' non autorisé."
            )
        return utilisateur

    return _verifier


def exiger_roles(*roles: str):
    """
    Fabrique une dépendance FastAPI qui exige un des rôles énumérés.

    Usage : `Utilisateur = Depends(exiger_roles("ADMIN", "RESPONSABLE"))`.
    """

    async def _verifier(
        utilisateur: dict = Depends(obtenir_utilisateur_actuel),
    ) -> dict:
        if not utilisateur.get("role") in roles or not role_valide(
            utilisateur.get("role")
        ):
            atteints = ", ".join(roles) if roles else "aucun"
            raise ErreurForbidden(
                f"Accès refusé : rôle requis parmi [{atteints}]."
            )
        return utilisateur

    return _verifier