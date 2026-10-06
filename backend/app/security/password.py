"""Hashage et vérification des mots de passe (bcrypt).

Les mots de passe ne sont **jamais** stockés en clair : seul le hash
bcrypt est persisté dans la collection `utilisateurs`.
"""

from __future__ import annotations

import bcrypt

COUT_HASHAGE = 12

TAILLE_STOCKEE_MAX_OCTETS = 72


def hash_mot_de_passe(mot_de_passe: str) -> str:
    """Hashage bcrypt du mot de passe (sel aléatoire par appel)."""
    sel = bcrypt.gensalt(rounds=COUT_HASHAGE)
    return bcrypt.hashpw(
        mot_de_passe.encode("utf-8"),
        sel,
    ).decode("ascii")


def verifier_mot_de_passe(mot_de_passe: str, hash_stocke: str) -> bool:
    """Vérifie un mot de passe contre son hash stocké (jamais en clair)."""
    if not hash_stocke:
        return False
    try:
        return bcrypt.checkpw(
            mot_de_passe.encode("utf-8"),
            hash_stocke.encode("ascii"),
        )
    except (ValueError, TypeError):
        return False