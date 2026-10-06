"""Crée le premier compte administrateur (si inexistant déjà).

Usage :
    ADMIN_EMAIL=admin@exemple.mg \
    ADMIN_MOT_DE_PASSE=MotDePasseTresLong123 \
    python scripts/generate_admin.py

Variables d'environnement :
    ADMIN_PRENOM (défaut : Administrateur)
    ADMIN_NOM (défaut : RFM)
    ADMIN_EMAIL (défaut : admin@rfm-srb.mg)
    ADMIN_MOT_DE_PASSE (obligatoire, >= 8 caractères)
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import connecter_database, fermer_database
from app.services.auth_service import creer_compte
from app.utils.errors import ApiError, ErreurConflict


async def main() -> int:
    mot_de_passe = os.getenv("ADMIN_MOT_DE_PASSE")
    if not mot_de_passe:
        print(
            "ERREUR : définissez ADMIN_MOT_DE_PASSE "
            "(>= 8 caractères, <= 72 octets)."
        )
        return 1

    prenom = os.getenv("ADMIN_PRENOM", "Administrateur")
    nom = os.getenv("ADMIN_NOM", "RFM")
    email = os.getenv("ADMIN_EMAIL", "admin@rfm-srb.mg")

    await connecter_database()
    try:
        reponse = await creer_compte(
            prenom=prenom,
            nom=nom,
            email=email,
            mot_de_passe=mot_de_passe,
            role="ADMIN",
        )
        utilisateur = reponse["utilisateur"]
        print(
            f"[OK] Compte administrateur créé : {utilisateur['email']} "
            f"({utilisateur['id']}) — le mot de passe n'est pas stocké en clair."
        )
        return 0
    except ErreurConflict:
        print(f"[OK] Un compte existe déjà pour : {email}")
        return 0
    except ApiError as erreur:
        print(f"[ÉCHEC] {erreur.code} : {erreur.message}")
        return 1
    finally:
        await fermer_database()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))