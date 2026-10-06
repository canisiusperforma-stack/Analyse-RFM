"""Modèle MongoDB de la collection `utilisateurs`.

Conforme à la proposition `docs/modele-donnees.md` :
- mot de passe stocké **uniquement** sous forme hashée (bcrypt) ;
- champ `role` contraint à l'énumération RBAC définie dans le service de
  permissions (source d'autorité : `app.services.permission_service`) ;
- les dates sont stockées en UTC (`datetime` timezone-aware).
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Optional

from app.services.permission_service import ROLES, ROLE_DEFAUT

EMAIL_REGEX = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def valider_email(email: str) -> bool:
    """Vérifie le format d'une adresse e-mail."""
    return bool(EMAIL_REGEX.match((email or "").strip()))


def role_valide(role: str) -> bool:
    return role in ROLES


def normaliser_email(email: str) -> str:
    """Normalise un e-mail : suppression des espaces, minuscules."""
    return (email or "").strip().lower()


def construire_utilisateur(
    *,
    prenom: str,
    nom: str,
    email: str,
    mot_de_passe_hash: str,
    role: Optional[str] = None,
    created_by: Optional[Any] = None,
) -> dict:
    """Construit le document `utilisateurs` avant insertion."""
    maintenant = datetime.now(timezone.utc)
    return {
        "prenom": prenom,
        "nom": nom,
        "email": normaliser_email(email),
        "mot_de_passe_hash": mot_de_passe_hash,
        "role": role if role in ROLES else ROLE_DEFAUT,
        "actif": True,
        "email_verifie": False,
        "derniere_connexion": None,
        "created_at": maintenant,
        "updated_at": maintenant,
        "created_by": created_by,
    }


def champs_publics(utilisateur: dict) -> dict:
    """Projette un utilisateur en sortie JSON sérialisable (jamais le hash)."""
    derniere_connexion = utilisateur.get("derniere_connexion")
    created_at = utilisateur.get("created_at")
    return {
        "id": str(utilisateur.get("_id", "")),
        "prenom": utilisateur.get("prenom"),
        "nom": utilisateur.get("nom"),
        "email": utilisateur.get("email"),
        "role": utilisateur.get("role"),
        "actif": utilisateur.get("actif", True),
        "email_verifie": utilisateur.get("email_verifie", False),
        "derniere_connexion": (
            derniere_connexion.isoformat() if derniere_connexion else None
        ),
        "created_at": created_at.isoformat() if created_at else None,
    }