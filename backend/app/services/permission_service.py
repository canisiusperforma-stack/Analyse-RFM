"""Service des permissions (source d'autorité du RBAC).

Le backend est l'autorité unique : chaque endpoint reçoit sa permission
via `app.security.permissions.exiger_permission(...)`. La matrice ci-dessous
est le référentiel commun aussi bien des contrôles serveur que de la
projection renvoyée au frontend (affichage uniquement).

Rôles :
    ADMIN        — accès total, gestion des utilisateurs ;
    RESPONSABLE  — pilotage et gestion opérationnelle (gestion des données) ;
    ANALYSTE     — lecture, analyses, prévisions, simulations, rapports ;
    AGENT        — opérationnel : gestion quotidienne (enregistrements).

Convention de nommage des permissions : `<module>:<action>`.

Base documentaire
    Le module `documents` sépare trois pouvoirs, volontairement distincts :

    - `documents:televerser`   déposer un fichier (classification `interne`) ;
    - `documents:indexer`      (re)construire les extraits d'un document ;
    - `documents:acces`        **fixer la confidentialité et la liste des
      autorisés**, donc modifier ce que chacun verra.

    `documents:acces` est réservé à `ADMIN`. Confier la classification à
    quiconque peut déjà téléverser reviendrait à laisser chacun décider de ce
    que les autres verront ; seul l'administrateur — dont le rôle est la seule
    destination prévue d'un incident — arbitre. `documents:indexer` est en
    revanche ouvert à `RESPONSABLE`, qui gère les données au quotidien :
    réindexer un fichier n'ouvre aucun accès et ne divulgue aucun contenu.

    Ces permissions gouvernent l'accès à la *fonction* ; l'accès à un *document*
    est filtré séparément et plus finement par
    `app.models.document.filtre_acces_documents`, au niveau de chaque extrait.
"""

from __future__ import annotations

from typing import FrozenSet, Set

from app.utils.errors import ErreurForbidden

ROLES = ("ADMIN", "RESPONSABLE", "ANALYSTE", "AGENT")
ROLE_DEFAUT = "AGENT"

MODULES = (
    "dashboard",
    "beneficiaires",
    "budget",
    "remboursements",
    "analyses",
    "anomalies",
    "previsions",
    "simulations",
    "assistant",
    "documents",
    "rapports",
    "utilisateurs",
    "importation",
)

PERMISSIONS: FrozenSet[str] = frozenset(
    {
        "dashboard:voir",
        "beneficiaires:voir",
        "beneficiaires:creer",
        "beneficiaires:modifier",
        "beneficiaires:supprimer",
        "beneficiaires:exporter",
        "budget:voir",
        "budget:creer",
        "budget:modifier",
        "budget:supprimer",
        "budget:exporter",
        "remboursements:voir",
        "remboursements:creer",
        "remboursements:modifier",
        "remboursements:supprimer",
        "remboursements:valider",
        "remboursements:exporter",
        "analyses:voir",
        "analyses:exporter",
        "anomalies:voir",
        "anomalies:traiter",
        "previsions:voir",
        "previsions:creer",
        "previsions:exporter",
        "simulations:voir",
        "simulations:creer",
        "simulations:supprimer",
        "simulations:exporter",
        "assistant:utiliser",
        "documents:voir",
        "documents:televerser",
        "documents:supprimer",
        "documents:telecharger",
        "documents:indexer",
        "documents:acces",
        "rapports:voir",
        "rapports:generer",
        "rapports:exporter",
        "utilisateurs:voir",
        "utilisateurs:creer",
        "utilisateurs:modifier",
        "utilisateurs:supprimer",
        "utilisateurs:changer_role",
        "importation:importer",
        "importation:voir_rapport",
    }
)

MATRICE_ROLES: dict[str, FrozenSet[str]] = {
    "ADMIN": frozenset(PERMISSIONS),
    "RESPONSABLE": frozenset(
        {
            "dashboard:voir",
            "beneficiaires:voir",
            "beneficiaires:creer",
            "beneficiaires:modifier",
            "beneficiaires:supprimer",
            "beneficiaires:exporter",
            "budget:voir",
            "budget:creer",
            "budget:modifier",
            "budget:supprimer",
            "budget:exporter",
            "remboursements:voir",
            "remboursements:creer",
            "remboursements:modifier",
            "remboursements:supprimer",
            "remboursements:valider",
            "remboursements:exporter",
            "analyses:voir",
            "analyses:exporter",
            "anomalies:voir",
            "anomalies:traiter",
            "previsions:voir",
            "previsions:creer",
            "previsions:exporter",
            "simulations:voir",
            "simulations:creer",
            "simulations:supprimer",
            "simulations:exporter",
            "assistant:utiliser",
            "documents:voir",
            "documents:televerser",
            "documents:supprimer",
            "documents:telecharger",
            "documents:indexer",
            "rapports:voir",
            "rapports:generer",
            "rapports:exporter",
            "utilisateurs:voir",
            "importation:importer",
            "importation:voir_rapport",
        }
    ),
    "ANALYSTE": frozenset(
        {
            "dashboard:voir",
            "beneficiaires:voir",
            "beneficiaires:exporter",
            "budget:voir",
            "budget:exporter",
            "remboursements:voir",
            "remboursements:exporter",
            "analyses:voir",
            "analyses:exporter",
            "anomalies:voir",
            "anomalies:traiter",
            "previsions:voir",
            "previsions:creer",
            "previsions:exporter",
            "simulations:voir",
            "simulations:creer",
            "simulations:exporter",
            "assistant:utiliser",
            "documents:voir",
            "documents:telecharger",
            "rapports:voir",
            "rapports:generer",
            "rapports:exporter",
            "importation:voir_rapport",
        }
    ),
    "AGENT": frozenset(
        {
            "dashboard:voir",
            "beneficiaires:voir",
            "beneficiaires:creer",
            "beneficiaires:modifier",
            "budget:voir",
            "remboursements:voir",
            "remboursements:creer",
            "remboursements:modifier",
            "analyses:voir",
            "anomalies:voir",
            "previsions:voir",
            "simulations:voir",
            "assistant:utiliser",
            "documents:voir",
            "documents:televerser",
            "documents:telecharger",
            "rapports:voir",
            "importation:importer",
        }
    ),
}


def role_valide(role: str) -> bool:
    return role in ROLES


def permissions_du_role(role: str) -> Set[str]:
    """Renvoie l'ensemble des permissions du rôle (vide si inconnu)."""
    return set(MATRICE_ROLES.get(role, frozenset()))


def utilisateur_a_permission(utilisateur: dict, permission: str) -> bool:
    """
    Détermine si un utilisateur dispose d'une permission.

    Politique de refus par défaut :
    - permission inconnue => refusée ;
    - rôle inconnu ou absent => refusé (aucun accès implicite).
    """
    if permission not in PERMISSIONS:
        return False
    return permission in permissions_du_role((utilisateur or {}).get("role"))


def permissions_utilisateur(utilisateur: dict) -> list[str]:
    """Permissions effectives d'un utilisateur (triées, pour l'UI)."""
    role = (utilisateur or {}).get("role")
    return sorted(permissions_du_role(role))


def verifier_permission(utilisateur: dict, permission: str) -> None:
    """Lève ErreurForbidden si l'utilisateur n'a pas la permission."""
    if not utilisateur_a_permission(utilisateur, permission):
        raise ErreurForbidden(
            f"Accès refusé : permission requise '{permission}'."
        )


def module_accessible(utilisateur: dict, module: str) -> bool:
    """True si l'utilisateur a au moins une permission du module."""
    return any(
        permission.startswith(f"{module}:")
        for permission in permissions_utilisateur(utilisateur)
    )


def permissions_du_module(module: str) -> Set[str]:
    """Toutes les permissions déclarées pour un module (vide si inconnu)."""
    return {
        permission
        for permission in PERMISSIONS
        if permission.startswith(f"{module}:")
    }


def modules_du_role(role: str) -> Set[str]:
    """Modules pour lesquels le rôle possède au moins une permission."""
    return {
        permission.split(":", 1)[0]
        for permission in permissions_du_role(role)
        if ":" in permission
    }


def modules_utilisateur(utilisateur: dict) -> list[str]:
    """Modules accessibles par un utilisateur (triés, pour l'UI)."""
    return sorted(modules_du_role((utilisateur or {}).get("role")))


def verifier_module(utilisateur: dict, module: str) -> None:
    """Lève ErreurForbidden si l'utilisateur n'a aucun accès au module."""
    if not module_accessible(utilisateur, module):
        raise ErreurForbidden(f"Accès refusé : module '{module}' non autorisé.")