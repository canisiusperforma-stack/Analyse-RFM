"""Logique métier de l'administration des utilisateurs (RBAC).

Ces opérations sont réservées aux rôles disposant des permissions
`utilisateurs:*` (ADMIN a l'accès complet, RESPONSABLE en lecture seule).
La vérification des permissions elle-même est effectuée par les
dépendances FastAPI (`app.security.permissions`) : ce service ne raisonne
que sur les règles métier (unicité, protections anti-verrouillage).
"""

from __future__ import annotations

from typing import Any, Optional

from bson import ObjectId
from pymongo.errors import DuplicateKeyError

from app.models.utilisateur import (
    champs_publics,
    construire_utilisateur,
    normaliser_email,
    valider_email,
)
from app.repositories.utilisateur_repository import (
    assurer_indexes,
    compter,
    creer,
    lister,
    mettre_a_jour,
    supprimer,
    trouver_par_email,
    trouver_par_id,
)
from app.security.password import hash_mot_de_passe
from app.services.permission_service import role_valide
from app.utils.errors import (
    ErreurConflict,
    ErreurNotFound,
    ErreurValidation,
)
from app.utils.logging import get_logger

logger = get_logger(__name__)


async def lister_utilisateurs(
    limite: int = 50,
    saut: int = 0,
    role: Optional[str] = None,
    actif: Optional[bool] = None,
) -> dict:
    """Liste paginée des comptes (profil public, jamais de hash)."""
    utilisateurs = await lister(limite=limite, saut=saut, role=role, actif=actif)
    total = await compter(role=role, actif=actif)
    return {
        "total": total,
        "limite": limite,
        "saut": saut,
        "utilisateurs": [champs_publics(u) for u in utilisateurs],
    }


async def creer_utilisateur(
    *,
    prenom: str,
    nom: str,
    email: str,
    mot_de_passe: str,
    role: str,
    created_by: Any = None,
) -> dict:
    """Crée un compte administré (sans émettre de jeton)."""
    await assurer_indexes()

    email_normalise = normaliser_email(email)
    if not valider_email(email_normalise):
        raise ErreurValidation("Adresse e-mail invalide.")
    if not role_valide(role):
        raise ErreurValidation("Rôle invalide.")

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
        "Compte créé par un administrateur : %s (rôle %s)",
        email_normalise,
        role,
    )
    return champs_publics(utilisateur)


async def mettre_a_jour_utilisateur(
    identifiant: Any,
    *,
    prenom: Optional[str] = None,
    nom: Optional[str] = None,
    actif: Optional[bool] = None,
) -> dict:
    """Met à jour les informations administratives d'un compte."""
    oid = _parser_identifiant(identifiant)
    if not await _existe(oid):
        raise ErreurNotFound("Utilisateur introuvable.")

    donnees: dict = {}
    if prenom is not None:
        donnees["prenom"] = prenom
    if nom is not None:
        donnees["nom"] = nom
    if actif is not None:
        donnees["actif"] = actif

    if not donnees:
        utilisateur = await trouver_par_id(oid)
        return champs_publics(utilisateur)

    utilisateur = await mettre_a_jour(oid, donnees)
    return champs_publics(utilisateur)


async def changer_role_utilisateur(
    identifiant: Any,
    *,
    role: str,
    acteur: dict,
) -> dict:
    """Change le rôle d'un compte (interdit sur son propre compte)."""
    oid = _parser_identifiant(identifiant)
    if not await _existe(oid):
        raise ErreurNotFound("Utilisateur introuvable.")
    if not role_valide(role):
        raise ErreurValidation("Rôle invalide.")

    if str(oid) == str(acteur.get("_id")):
        raise ErreurValidation(
            "Impossible de modifier votre propre rôle "
            "(cela pourrait verrouiller la plateforme)."
        )

    utilisateur = await mettre_a_jour(oid, {"role": role})
    logger.info(
        "Rôle %s attribué à %s (par %s)",
        role,
        utilisateur.get("email"),
        acteur.get("email"),
    )
    return champs_publics(utilisateur)


async def supprimer_utilisateur(identifiant: Any, acteur: dict) -> None:
    """Supprime définitivement un compte (jamais son propre compte)."""
    oid = _parser_identifiant(identifiant)
    utilisateur = await trouver_par_id(oid)
    if utilisateur is None:
        raise ErreurNotFound("Utilisateur introuvable.")

    if str(oid) == str(acteur.get("_id")):
        raise ErreurValidation(
            "Impossible de supprimer votre propre compte."
        )

    await supprimer(oid)
    logger.info(
        "Compte supprimé : %s (par %s)",
        utilisateur.get("email"),
        acteur.get("email"),
    )


def _parser_identifiant(identifiant: Any) -> ObjectId:
    try:
        return ObjectId(identifiant)
    except Exception:
        raise ErreurNotFound("Utilisateur introuvable.")


async def _existe(identifiant: ObjectId) -> bool:
    return await trouver_par_id(identifiant) is not None