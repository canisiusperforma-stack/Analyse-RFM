"""Génère le bloc de données RBAC dans `frontend/lib/permissions.js`.

Le backend (`app/services/permission_service.py`) est la seule source de
vérité des rôles, modules et permissions. Ce script projette la matrice
vers le frontend pour l'affichage/masquage uniquement (jamais pour la
sécurité, le backend restant l'autorité).

Le fichier `frontend/lib/permissions.js` contient :
- un bloc de données délimité par les marqueurs `//RBAC_DONNEES_DEBUT` /
  `//RBAC_DONNEES_FIN`, régénéré ici ;
- des fonctions utilitaires écrites à la main, conservées telles quelles.

Usage :
    python backend/scripts/generer_permissions_frontend.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.permission_service import (  # noqa: E402
    MATRICE_ROLES,
    MODULES,
    PERMISSIONS,
    ROLES,
    ROLE_DEFAUT,
)

SORTIE = (
    Path(__file__).resolve().parent.parent.parent
    / "frontend"
    / "lib"
    / "permissions.js"
)

MARQUEUR_DEBUT = "//RBAC_DONNEES_DEBUT"
MARQUEUR_FIN = "//RBAC_DONNEES_FIN"


def _organiser() -> str:
    roles = sorted(ROLES)
    modules = sorted(MODULES)
    permissions = sorted(PERMISSIONS)

    def liste(noms: list[str]) -> str:
        corps = ",\n    ".join(f'"{nom}"' for nom in noms)
        return f"[\n    {corps}\n  ]"

    champs = [
        "// Données générées automatiquement — source d'autorité :",
        "// backend/app/services/permission_service.py. Ne pas modifier à la main.",
        f"export const ROLES = {liste(roles)};",
        f'export const ROLE_DEFAUT = "{ROLE_DEFAUT}";',
        f"export const MODULES = {liste(modules)};",
        f"export const PERMISSIONS = {liste(permissions)};",
        "export const PERMISSIONS_PAR_ROLE = {",
    ]
    for role in roles:
        champs.append(f'  "{role}": {liste(sorted(MATRICE_ROLES[role]))},')
    champs.append("};")
    return "\n\n".join(champs) + "\n"


def main() -> int:
    if not SORTIE.exists():
        print(
            f"ERREUR : {SORTIE} introuvable. "
            f"Créez-le avec les marqueurs {MARQUEUR_DEBUT} / {MARQUEUR_FIN}."
        )
        return 1

    contenu = SORTIE.read_text(encoding="utf-8")
    if MARQUEUR_DEBUT not in contenu or MARQUEUR_FIN not in contenu:
        print(
            f"ERREUR : marqueurs {MARQUEUR_DEBUT} / {MARQUEUR_FIN} "
            f"absents de {SORTIE}."
        )
        return 1

    avant = contenu.split(MARQUEUR_DEBUT, 1)[0]
    apres = contenu.split(MARQUEUR_FIN, 1)[1]
    bloc = (
        f"{MARQUEUR_DEBUT}\n"
        + _organiser().rstrip("\n")
        + f"\n{MARQUEUR_FIN}"
    )
    SORTIE.write_text(avant + bloc + apres, encoding="utf-8")
    print(f"[OK] {SORTIE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())