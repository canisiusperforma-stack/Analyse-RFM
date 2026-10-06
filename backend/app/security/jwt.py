"""Création, vérification et décodage des jetons JWT.

- Jetons signés en HS256 via python-jose ;
- durée de validité configurable (`JWT_EXPIRATION_MINUTES`) ;
- `exp`/`iat` contrôlés à chaque décodage, émetteur vérifié (`iss`) ;
- `sub` = identifiant ObjectId de l'utilisateur, `jti` pour l'unicité.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from jose import JWTError, jwt
from jose.exceptions import ExpiredSignatureError

from app.config import settings
from app.utils.errors import ErreurUnauthorized


def creer_jeton(
    utilisateur: dict,
    expiration_minutes: Optional[int] = None,
) -> tuple[str, int]:
    """Crée un jeton d'accès et renvoie (jeton, durée_en_secondes)."""
    duree = expiration_minutes or settings.JWT_EXPIRATION_MINUTES
    maintenant = datetime.now(timezone.utc)
    expiration = maintenant + timedelta(minutes=duree)

    charge: dict[str, Any] = {
        "sub": str(utilisateur["_id"]),
        "email": utilisateur.get("email"),
        "role": utilisateur.get("role"),
        "iat": maintenant,
        "exp": expiration,
        "iss": settings.JWT_ISSUER,
        "jti": uuid.uuid4().hex,
    }

    jeton = jwt.encode(
        charge,
        settings.JWT_SECRET,
        algorithm=settings.JWT_ALGORITHM,
    )
    return jeton, int(duree * 60)


def decoder_jeton(jeton: str) -> dict:
    """Vérifie la signature, l'expiration et retourne la charge utile."""
    try:
        return jwt.decode(
            jeton,
            settings.JWT_SECRET,
            algorithms=[settings.JWT_ALGORITHM],
            issuer=settings.JWT_ISSUER,
            options={
                "require": ["sub", "exp", "iat", "iss"],
                "verify_signature": True,
                "verify_exp": True,
                "verify_iat": True,
            },
        )
    except ExpiredSignatureError:
        raise ErreurUnauthorized(
            "Session expirée. Veuillez vous reconnecter."
        )
    except JWTError:
        raise ErreurUnauthorized(
            "Jeton d'authentification invalide ou illisible."
        )


def decoder_jeton_ignorer_expiration(jeton: str) -> dict:
    """Décode la charge utile sans vérifier l'expiration (tests)."""
    try:
        return jwt.decode(
            jeton,
            settings.JWT_SECRET,
            algorithms=[settings.JWT_ALGORITHM],
            options={
                "verify_exp": False,
                "require": ["sub"],
            },
        )
    except JWTError:
        raise ErreurUnauthorized(
            "Jeton d'authentification invalide ou illisible."
        )