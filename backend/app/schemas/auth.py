"""Schémas Pydantic de l'authentification."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field, field_validator

from app.models.utilisateur import (
    ROLE_DEFAUT,
    ROLES,
    normaliser_email,
    role_valide,
    valider_email,
)

LONGUEUR_MIN_MOT_DE_PASSE = 8
TAILLE_MAX_MOT_DE_PASSE_OCTETS = 72


class CreationCompteSchema(BaseModel):
    """Corps de requête de création de compte."""

    prenom: str = Field(min_length=1, max_length=100, description="Prénom")
    nom: str = Field(min_length=1, max_length=100, description="Nom")
    email: str = Field(description="Adresse e-mail (unique)")
    mot_de_passe: str = Field(
        min_length=LONGUEUR_MIN_MOT_DE_PASSE,
        max_length=TAILLE_MAX_MOT_DE_PASSE_OCTETS,
        description=(
            "Mot de passe (8 caractères minimum, 72 octets maximum)"
        ),
    )
    role: Optional[str] = Field(
        default=None,
        description=f"Rôle optionnel (défaut : {ROLE_DEFAUT})",
    )

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
    def _valider_role(cls, valeur: Optional[str]) -> Optional[str]:
        if valeur is None or valeur == "":
            return None
        if not role_valide(valeur):
            raise ValueError(
                f"Rôle invalide. Valeurs possibles : {', '.join(ROLES)}."
            )
        return valeur


class ConnexionSchema(BaseModel):
    """Corps de requête de connexion."""

    email: str = Field(description="Adresse e-mail")
    mot_de_passe: str = Field(description="Mot de passe")

    @field_validator("email")
    @classmethod
    def _valider_email(cls, valeur: str) -> str:
        return normaliser_email(valeur)