"""Schémas Pydantic de l'administration des utilisateurs (RBAC)."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field, field_validator

from app.models.utilisateur import normaliser_email, role_valide, valider_email
from app.services.permission_service import ROLES

LONGUEUR_MIN_MOT_DE_PASSE = 8
TAILLE_MAX_MOT_DE_PASSE_OCTETS = 72


class CreationUtilisateurSchema(BaseModel):
    """Création d'un compte par un administrateur."""

    prenom: str = Field(min_length=1, max_length=100, description="Prénom")
    nom: str = Field(min_length=1, max_length=100, description="Nom")
    email: str = Field(description="Adresse e-mail (unique)")
    mot_de_passe: str = Field(
        min_length=LONGUEUR_MIN_MOT_DE_PASSE,
        max_length=TAILLE_MAX_MOT_DE_PASSE_OCTETS,
        description="Mot de passe provisoire (8 caractères minimum).",
    )
    role: str = Field(description=f"Rôle RBAC : {', '.join(ROLES)}.")

    @field_validator("prenom", "nom")
    @classmethod
    def _nettoyer_texte(cls, valeur: str) -> str:
        nettoye = (valeur or "").strip()
        if not nettoye:
            raise ValueError("Ce champ est obligatoire.")
        return nettoye

    @field_validator("email")
    @classmethod
    def _valider_email(cls, valeur: str) -> str:
        email = normaliser_email(valeur)
        if not valider_email(email):
            raise ValueError("Adresse e-mail invalide.")
        return email

    @field_validator("role")
    @classmethod
    def _valider_role(cls, valeur: str) -> str:
        if not role_valide(valeur):
            raise ValueError(f"Rôle invalide. Valeurs possibles : {', '.join(ROLES)}.")
        return valeur


class MiseAJourUtilisateurSchema(BaseModel):
    """Modification des informations administratives d'un compte."""

    prenom: Optional[str] = Field(default=None, min_length=1, max_length=100)
    nom: Optional[str] = Field(default=None, min_length=1, max_length=100)
    actif: Optional[bool] = Field(
        default=None, description="Active / désactive le compte."
    )

    @field_validator("prenom", "nom")
    @classmethod
    def _nettoyer_texte(cls, valeur: Optional[str]) -> Optional[str]:
        if valeur is None:
            return None
        nettoye = (valeur or "").strip()
        if not nettoye:
            raise ValueError("Ce champ ne peut pas être vide.")
        return nettoye


class ChangerRoleSchema(BaseModel):
    """Attribution d'un nouveau rôle RBAC."""

    role: str = Field(description=f"Rôle RBAC : {', '.join(ROLES)}.")

    @field_validator("role")
    @classmethod
    def _valider_role(cls, valeur: str) -> str:
        if not role_valide(valeur):
            raise ValueError(f"Rôle invalide. Valeurs possibles : {', '.join(ROLES)}.")
        return valeur