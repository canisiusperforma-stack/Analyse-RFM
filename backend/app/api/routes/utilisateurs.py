"""Routes d'administration des utilisateurs (RBAC, réservées aux rôles autorisés).

- `GET/POST /utilisateurs`        : `utilisateurs:voir` / `utilisateurs:creer`
- `PATCH /utilisateurs/{id}`      : `utilisateurs:modifier`
- `PATCH /utilisateurs/{id}/role` : `utilisateurs:changer_role`
- `DELETE /utilisateurs/{id}`     : `utilisateurs:supprimer`
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.schemas.utilisateur import (
    ChangerRoleSchema,
    CreationUtilisateurSchema,
    MiseAJourUtilisateurSchema,
)
from app.security.permissions import exiger_permission
from app.services.utilisateur_service import (
    changer_role_utilisateur,
    creer_utilisateur,
    lister_utilisateurs,
    mettre_a_jour_utilisateur,
    supprimer_utilisateur,
)

router = APIRouter()


@router.get(
    "",
    summary="Lister les utilisateurs",
    description="Liste paginée des comptes (profil public uniquement).",
)
async def lister(
    _: dict = Depends(exiger_permission("utilisateurs:voir")),
    limite: int = Query(50, ge=1, le=500),
    saut: int = Query(0, ge=0),
    role: str | None = Query(None, description="Filtre par rôle RBAC."),
    actif: bool | None = Query(None, description="Filtre par état du compte."),
):
    return await lister_utilisateurs(
        limite=limite, saut=saut, role=role, actif=actif
    )


@router.post(
    "",
    status_code=201,
    summary="Créer un utilisateur",
    description="Crée un compte avec un rôle RBAC (mot de passe hashé).",
)
async def creer(
    donnees: CreationUtilisateurSchema,
    acteur: dict = Depends(exiger_permission("utilisateurs:creer")),
):
    return await creer_utilisateur(
        prenom=donnees.prenom,
        nom=donnees.nom,
        email=donnees.email,
        mot_de_passe=donnees.mot_de_passe,
        role=donnees.role,
        created_by=acteur.get("_id"),
    )


@router.patch(
    "/{identifiant}",
    summary="Modifier un utilisateur",
    description="Modifie prénom, nom ou état (actif/inactif) d'un compte.",
)
async def modifier(
    identifiant: str,
    donnees: MiseAJourUtilisateurSchema,
    _: dict = Depends(exiger_permission("utilisateurs:modifier")),
):
    return await mettre_a_jour_utilisateur(
        identifiant,
        prenom=donnees.prenom,
        nom=donnees.nom,
        actif=donnees.actif,
    )


@router.patch(
    "/{identifiant}/role",
    summary="Changer le rôle d'un utilisateur",
    description="Réattribue un rôle RBAC (interdit sur son propre compte).",
)
async def changer_role(
    identifiant: str,
    donnees: ChangerRoleSchema,
    acteur: dict = Depends(exiger_permission("utilisateurs:changer_role")),
):
    return await changer_role_utilisateur(
        identifiant,
        role=donnees.role,
        acteur=acteur,
    )


@router.delete(
    "/{identifiant}",
    status_code=204,
    summary="Supprimer un utilisateur",
    description="Supprime définitivement un compte (jamais son propre compte).",
)
async def supprimer(
    identifiant: str,
    acteur: dict = Depends(exiger_permission("utilisateurs:supprimer")),
):
    await supprimer_utilisateur(identifiant, acteur=acteur)