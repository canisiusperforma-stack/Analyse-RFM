"""Logique métier de l'authentification (compte, connexion, session)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from pymongo.errors import DuplicateKeyError

from app.models.utilisateur import (
    champs_publics,
    construire_utilisateur,
    normaliser_email,
    role_valide,
    valider_email,
)
from app.repositories.utilisateur_repository import (
    assurer_indexes,
    creer,
    mettre_a_jour_derniere_connexion,
    trouver_par_email,
    trouver_par_id,
)
from app.security.jwt import creer_jeton
from app.security.password import hash_mot_de_passe, verifier_mot_de_passe
from app.services.permission_service import (
    ROLES,
    permissions_utilisateur,
)
from app.utils.errors import ErreurConflict, ErreurUnauthorized, ErreurValidation
from app.utils.logging import get_logger

logger = get_logger(__name__)


async def creer_compte(
    *,
    prenom: str,
    nom: str,
    email: str,
    mot_de_passe: str,
    role: Optional[str] = None,
    created_by: Optional[Any] = None,
) -> dict:
    """
    Crée un compte utilisateur et renvoie la réponse d'authentification
    (jeton + utilisateur public).

    Le mot de passe est hashé (bcrypt) avant persistance : il n'est jamais
    stocké ni restitué en clair.
    """
    await assurer_indexes()

    email_normalise = normaliser_email(email)
    if not valider_email(email_normalise):
        raise ErreurValidation("Adresse e-mail invalide.")
    if role and not role_valide(role):
        raise ErreurValidation(
            f"Rôle invalide : '{role}'. "
            f"Valeurs possibles : {', '.join(ROLES)}."
        )

    if await trouver_par_email(email_normalise) is not None:
        raise ErreurConflict(
            "Un compte existe déjà avec cette adresse e-mail."
        )

    utilisateur = construire_utilisateur(
        prenom=prenom,
        nom=nom,
        email=email_normalise,
        mot_de_passe_hash=hash_mot_de_passe(mot_de_passe),
        role=role,
        created_by=created_by,
    )

    try:
        identifiant = await creer(utilisateur)
    except DuplicateKeyError:
        raise ErreurConflict(
            "Un compte existe déjà avec cette adresse e-mail."
        )

    utilisateur["_id"] = identifiant
    logger.info(
        "Compte créé : %s (%s)",
        email_normalise,
        utilisateur.get("role"),
    )
    return construire_reponse_authentification(utilisateur)


async def connecter(email: str, mot_de_passe: str) -> dict:
    """
    Authentifie un utilisateur et renvoie un jeton d'accès.

    Échec d'identification ou désactivation du compte => 401, sans
    révéler si l'e-mail existe (protection contre l'énumération).
    """
    utilisateur = await trouver_par_email(normaliser_email(email))
    if utilisateur is None or not verifier_mot_de_passe(
        mot_de_passe,
        utilisateur.get("mot_de_passe_hash") or "",
    ):
        raise ErreurUnauthorized("Identifiants incorrects.")

    if not utilisateur.get("actif", True):
        raise ErreurUnauthorized("Ce compte est désactivé.")

    await mettre_a_jour_derniere_connexion(utilisateur["_id"])
    logger.info("Connexion réussie : %s", utilisateur.get("email"))
    return construire_reponse_authentification(utilisateur)


async def obtenir_utilisateur_connecte(identifiant: Any) -> dict:
    """Retrouve l'utilisateur courant depuis son identifiant (sub)."""
    if identifiant is None:
        raise ErreurUnauthorized("Authentification requise.")

    utilisateur = await trouver_par_id(identifiant)
    if utilisateur is None:
        raise ErreurUnauthorized(
            "L'utilisateur associé au jeton n'existe plus."
        )
    if not utilisateur.get("actif", True):
        raise ErreurUnauthorized("Ce compte est désactivé.")
    return utilisateur


def construire_reponse_authentification(utilisateur: dict) -> dict:
    """Construit la réponse de connexion : jeton + expiration + utilisateur."""
    jeton, duree_secondes = creer_jeton(utilisateur)
    expiration = datetime.now(timezone.utc) + timedelta(seconds=duree_secondes)
    return {
        "access_token": jeton,
        "token_type": "bearer",
        "expires_in": duree_secondes,
        "expires_at": expiration.isoformat(),
        "utilisateur": champs_publics(utilisateur),
        "permissions": permissions_utilisateur(utilisateur),
    }