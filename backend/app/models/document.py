"""Modèle MongoDB de la collection `documents` et politique de confidentialité.

Conforme à `docs/modele-donnees.md` (§ 3.10) pour les champs déjà décrits
(`nom_fichier`, `type_mime`, `file_id`, `statut_indexation`, `cree_par`,
`created_at`, `updated_at`), et complété ici par les attributs qu'exige la
recherche documentaire : classification de confidentialité et droits d'accès
nominatifs.

Confidentialité
    Trois niveaux, du plus ouvert au plus fermé :

    | Niveau             | Qui peut lire                                        |
    |--------------------|------------------------------------------------------|
    | `interne`          | tout utilisateur disposant de `documents:voir`       |
    | `restreinte`       | rôles listés dans `roles_autorises`                  |
    | `confidentielle`   | rôles **et** utilisateurs listés (liste blanche)     |

    La règle est celle du refus par défaut, déjà appliquée au RBAC
    (`app.services.permission_service`) : un champ absent vaut `interne` pour
    que les documents déposés avant l'existence de la classification restent
    lisibles, mais un rôle absent de `roles_autorises` n'accède jamais à un
    document restreint ou confidentiel. `ADMIN` n'a pas de passe-droit : c'est
    l'administrateur qui figure dans la liste blanche, ce qui évite qu'une
    fuite de compte administrateur suffise à exposer un document sensible.

Le filtrage est appliqué **par la base**, via `filtre_acces_documents`, et non
après lecture : un morceau non autorisé n'est jamais chargé, jamais scoré,
jamais intégré au contexte du modèle. `filtre_acces_documents` est donc la
seule fonction à utiliser pour construire une requête de lecture, et
`app.rag.retriever` la ré-applique sur chaque morceau rendu (défense en
profondeur : une erreur de construction de filtre ne doit pas suffire à
divulguer un extrait).
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any, Optional

from app.services.permission_service import ROLES

# --- Niveaux de confidentialité --------------------------------------------

CONFIDENTIALITE_INTERNE = "interne"
CONFIDENTIALITE_RESTREINTE = "restreinte"
CONFIDENTIALITE_CONFIDENTIELLE = "confidentielle"

NIVEAUX_CONFIDENTIALITE = (
    CONFIDENTIALITE_INTERNE,
    CONFIDENTIALITE_RESTREINTE,
    CONFIDENTIALITE_CONFIDENTIELLE,
)

#: Niveau appliqué lorsqu'aucun n'est fourni à l'import.
NIVEAU_DEFAUT = CONFIDENTIALITE_INTERNE

# --- États d'indexation ----------------------------------------------------

STATUT_EN_ATTENTE = "en_attente"
STATUT_INDEXE = "indexe"
STATUT_ECHEC = "echec"

STATUTS_INDEXATION = (STATUT_EN_ATTENTE, STATUT_INDEXE, STATUT_ECHEC)

# --- Types MIME acceptés ---------------------------------------------------

TYPES_MIME: dict[str, str] = {
    "pdf": "application/pdf",
    "txt": "text/plain",
    "md": "text/markdown",
    "csv": "text/csv",
    "json": "application/json",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


def confidentialite_valide(niveau: Any) -> bool:
    return niveau in NIVEAUX_CONFIDENTIALITE


def normaliser_niveau(niveau: Optional[str]) -> str:
    """Normalise un niveau : inconnu ou absent ⇒ `interne` (jamais plus ouvert)."""
    if confidentialite_valide(niveau):
        return str(niveau)
    return NIVEAU_DEFAUT


def normaliser_roles(roles: Optional[list[str]]) -> list[str]:
    """Ne conserve que les rôles connus du RBAC, sans doublon ni ordre imposé."""
    if not roles:
        return []
    return sorted({str(role) for role in roles if str(role) in ROLES})


def type_mime_de_extension(extension: str) -> str:
    """Type MIME déduit de l'extension, ou type générique si inconnue."""
    return TYPES_MIME.get(extension.lower().lstrip("."), "application/octet-stream")


def extension_de_nom(nom_fichier: Optional[str]) -> str:
    """Extension normalisée d'un nom de fichier (sans point, en minuscules)."""
    if not nom_fichier or "." not in nom_fichier:
        return ""
    return nom_fichier.rsplit(".", 1)[-1].strip().lower()


def sha256(contenu: bytes) -> str:
    """Empreinte du contenu : doublons et intégrité du fichier d'origine."""
    return hashlib.sha256(contenu).hexdigest()


# --- Construction du document ---------------------------------------------


def construire_document(
    *,
    nom_fichier: str,
    contenu: bytes,
    type_mime: Optional[str] = None,
    description: Optional[str] = None,
    confidentialite: Optional[str] = None,
    roles_autorises: Optional[list[str]] = None,
    utilisateurs_autorises: Optional[list[Any]] = None,
    file_id: Optional[Any] = None,
    cree_par: Optional[Any] = None,
    source: str = "televersement",
) -> dict[str, Any]:
    """Construit le document `documents` avant insertion.

    La classification est normalisée avant stockage : un niveau inconnu ou
    absent devient `interne`, et les rôles demandés sont recoupés avec le RBAC.
    Un document `restreinte` ou `confidentielle` sans aucun rôle autorisé est
    refusé ici plutôt qu'indexé : il serait inaccessible à tout le monde, donc
    inerte dans la base documentaire.
    """
    niveau = normaliser_niveau(confidentialite)
    roles = normaliser_roles(roles_autorises)
    utilisateurs = sorted({str(identifiant) for identifiant in (utilisateurs_autorises or [])})

    if niveau in (CONFIDENTIALITE_RESTREINTE, CONFIDENTIALITE_CONFIDENTIELLE) and not roles:
        raise ValueError(
            f"Un document « {niveau} » doit désigner au moins un rôle autorisé."
        )

    extension = extension_de_nom(nom_fichier)
    maintenant = datetime.now(timezone.utc)
    return {
        "nom_fichier": nom_fichier,
        "type_mime": type_mime or type_mime_de_extension(extension),
        "extension": extension,
        "taille_octets": len(contenu),
        "sha256": sha256(contenu),
        "description": description or None,
        "source": source,
        "file_id": file_id,
        "confidentialite": niveau,
        "roles_autorises": roles,
        "utilisateurs_autorises": utilisateurs,
        "statut_indexation": STATUT_EN_ATTENTE,
        "nb_morceaux": 0,
        "cree_par": cree_par,
        "created_at": maintenant,
        "updated_at": maintenant,
    }


# --- Autorisation ----------------------------------------------------------


def document_visible(
    document: dict[str, Any],
    utilisateur: Optional[dict[str, Any]],
) -> bool:
    """Le document est-il lisible par cet utilisateur ?

    Rappel du contrat : `utilisateur` peut être `None` (usage interne, ou
    appel sans session). Dans ce cas l'accès est refusé pour tout document
    classifié, et autorisé pour un document `interne` — la base reste ainsi
    inexploitable sans identité.
    """
    niveau = normaliser_niveau((document or {}).get("confidentialite"))

    if niveau == CONFIDENTIALITE_INTERNE:
        return True

    if not utilisateur:
        return False

    role = utilisateur.get("role")
    if role not in (document.get("roles_autorises") or []):
        return False

    if niveau == CONFIDENTIALITE_CONFIDENTIELLE:
        identifiant = utilisateur.get("_id") or utilisateur.get("id")
        if identifiant is None:
            return False
        return str(identifiant) in {
            str(autorise) for autorise in (document.get("utilisateurs_autorises") or [])
        }

    return True


def filtre_acces_documents(utilisateur: Optional[dict[str, Any]]) -> dict[str, Any]:
    """Clause MongoDB ne retenant que les documents lisibles par l'utilisateur.

    Cette clause est la barrière d'accès du RAG. Elle est appliquée dans la
    requête de la collection, **avant** tout calcul de similarité : un morceau
    non autorisé n'est jamais lu en base, jamais vectorisé, jamais inséré dans
    le contexte et ne peut donc pas fuiter, même par un journal de débogage ou
    une citation.

    `$or` explicite plutôt qu'un `$and` de conditions : un document `interne`
    n'a pas de `roles_autorises`, et une condition unique portant sur le rôle
    l'exclurait à tort. Le champ `confidentialite` peut être absent sur des
    documents antérieurs à la classification ; `None` dans le `$in` le traite
    alors comme `interne`.
    """
    role = (utilisateur or {}).get("role")
    identifiant = (utilisateur or {}).get("_id") or (utilisateur or {}).get("id")

    branches: list[dict[str, Any]] = [
        {"confidentialite": {"$in": [CONFIDENTIALITE_INTERNE, None]}},
    ]

    if role:
        branches.append({
            "confidentialite": CONFIDENTIALITE_RESTREINTE,
            "roles_autorises": role,
        })
        if identifiant is not None:
            branches.append({
                "confidentialite": CONFIDENTIALITE_CONFIDENTIELLE,
                "roles_autorises": role,
                "utilisateurs_autorises": str(identifiant),
            })

    return {"$or": branches}


def peut_gerer_acces(utilisateur: Optional[dict[str, Any]]) -> bool:
    """Droit de fixer la classification et la liste des autorisés.

    Réservé à `ADMIN`. La classification restreint l'accès au document : la
    confier à quiconque peut déjà le téléverser reviendrait à laisser chacun
    décider de ce que les autres verront. Seul l'administrateur — dont le rôle
    est l'unique destination prévue d'un incident — arbitre.
    """
    return (utilisateur or {}).get("role") == "ADMIN"


def resumer(document: dict[str, Any]) -> dict[str, Any]:
    """Projection publique d'un document (jamais de vecteur ni d'identifiant interne)."""
    created_at = document.get("created_at")
    updated_at = document.get("updated_at")
    cree_par = document.get("cree_par")
    return {
        "id": str(document.get("_id", "")),
        "nom_fichier": document.get("nom_fichier"),
        "type_mime": document.get("type_mime"),
        "taille_octets": document.get("taille_octets"),
        "description": document.get("description"),
        "confidentialite": normaliser_niveau(document.get("confidentialite")),
        "roles_autorises": document.get("roles_autorises") or [],
        "utilisateurs_autorises": [str(item) for item in (document.get("utilisateurs_autorises") or [])],
        "statut_indexation": document.get("statut_indexation"),
        "nb_morceaux": document.get("nb_morceaux", 0),
        "extension": document.get("extension", ""),
        "cree_par": str(cree_par) if cree_par else None,
        "created_at": created_at.isoformat() if created_at else None,
        "updated_at": updated_at.isoformat() if updated_at else None,
    }
