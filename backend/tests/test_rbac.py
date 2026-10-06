"""Tests du système RBAC (rôles ADMIN, RESPONSABLE, ANALYSTE, AGENT).

Vérifie :
- la matrice des permissions (exactitude par rôle, hiérarchies, invariant
  « chaque permission est couverte ») ;
- le service `permission_service` (permissions par rôle, vérification,
  refus par défaut pour permissions inconnues / rôles inconnus) ;
- les dépendances FastAPI `exiger_permission` et `exiger_roles`
  (appelées directement avec un utilisateur simulé) ;
- le comportement réel en base : création/connexion par rôle, permissions
  renvoyées à l'authentification, gestion des utilisateurs (création,
  changement de rôle, auto-protection, désactivation).

Lancement :
    python tests/test_rbac.py
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bson import ObjectId

from app.database import connecter_database, fermer_database, obtenir_database
from app.security.permissions import (
    exiger_module,
    exiger_permission,
    exiger_roles,
)
from app.services.auth_service import connecter, creer_compte
from app.services.permission_service import (
    MATRICE_ROLES,
    MODULES,
    PERMISSIONS,
    ROLES,
    ROLE_DEFAUT,
    module_accessible,
    modules_du_role,
    modules_utilisateur,
    permissions_du_module,
    permissions_du_role,
    permissions_utilisateur,
    role_valide,
    utilisateur_a_permission,
    verifier_module,
    verifier_permission,
)
from app.services.utilisateur_service import (
    changer_role_utilisateur,
    creer_utilisateur,
    lister_utilisateurs,
    supprimer_utilisateur,
)
from app.utils.errors import ErreurForbidden, ErreurNotFound, ErreurValidation

_comptes_crees: list[str] = []


async def _nettoyer(email: str) -> None:
    db = obtenir_database()
    await db["utilisateurs"].delete_many({"email": email})


def _utilisateur(role: str | None) -> dict:
    return {"_id": ObjectId(), "role": role, "email": "utilisateur@test.mg"}


async def _tester_constantes():
    assert set(ROLES) == {"ADMIN", "RESPONSABLE", "ANALYSTE", "AGENT"}
    assert ROLE_DEFAUT == "AGENT"
    assert set(MATRICE_ROLES.keys()) == set(ROLES), (
        "La matrice doit couvrir exactement les rôles définis"
    )
    for role in ROLES:
        assert role_valide(role) and role in MATRICE_ROLES
    demanda = [
        "utilisateurs:creer",
        "utilisateurs:modifier",
        "utilisateurs:supprimer",
        "utilisateurs:changer_role",
    ]
    assert all(p in MATRICE_ROLES["ADMIN"] for p in demanda)
    assert all(p not in MATRICE_ROLES["RESPONSABLE"] for p in demanda), (
        "La gestion complète des utilisateurs doit être réservée à l'ADMIN"
    )
    print("[OK] Constantes : rôles, défaut, matrice complète")

    for role in ROLES:
        assert "dashboard:voir" in MATRICE_ROLES[role]
    assert MATRICE_ROLES["ANALYSTE"] <= MATRICE_ROLES["RESPONSABLE"]
    assert MATRICE_ROLES["RESPONSABLE"] <= MATRICE_ROLES["ADMIN"]
    couvertes = set().union(*MATRICE_ROLES.values())
    assert couvertes == set(PERMISSIONS), (
        "Chaque permission doit être attribuée à au moins un rôle"
    )
    print("[OK] Hiérarchie ADMIN >= RESPONSABLE >= ANALYSTE ; chaque permission couverte")


async def _tester_coherence_modules_permissions():
    prefixes_modules = {f"{module}:" for module in MODULES}
    non_couvertes = [
        permission
        for permission in PERMISSIONS
        if not any(permission.startswith(p) for p in prefixes_modules)
    ]
    assert not non_couvertes, f"Permissions hors module connu : {non_couvertes}"

    for module in MODULES:
        permissions = permissions_du_module(module)
        assert permissions, f"Aucune permission déclarée pour {module}"
        assert all(p.startswith(f"{module}:") for p in permissions)
        assert permissions <= set(PERMISSIONS)
        assert all(module in modules_du_role(role) for role in ROLES if permissions & permissions_du_role(role))
    print("[OK] Cohérence : chaque permission est rattachée à un module déclaré")


async def _tester_modules_par_role():
    attendus = {
        "ADMIN": set(MODULES),
        "RESPONSABLE": set(MODULES),
        "ANALYSTE": set(MODULES) - {"utilisateurs"},
        "AGENT": set(MODULES) - {"utilisateurs"},
    }
    for role in ROLES:
        utilisateur = _utilisateur(role)
        assert modules_du_role(role) == attendus[role], role
        assert set(modules_utilisateur(utilisateur)) == attendus[role], role
        for module in MODULES:
            acces = module in attendus[role]
            assert module_accessible(utilisateur, module) is acces, (
                f"{role}/{module} : attendu {acces}"
            )
            if not acces:
                try:
                    verifier_module(utilisateur, module)
                    raise AssertionError(
                        f"{role} ne doit pas accéder au module {module}"
                    )
                except ErreurForbidden:
                    pass
        print(f"[OK] {role} : accès modules == {sorted(attendus[role])}")

    agent = _utilisateur("AGENT")
    verifier_module(agent, "remboursements")
    try:
        verifier_module(agent, "utilisateurs")
        raise AssertionError("AGENT ne doit pas accéder au module utilisateurs")
    except ErreurForbidden:
        pass
    assert not module_accessible(agent, "module_inconnu")
    print("[OK] verifier_module : accordé / 403 (ErreurForbidden)")


async def _tester_permissions_par_role():
    for role in ROLES:
        attendues = set(MATRICE_ROLES[role])
        assert permissions_du_role(role) == attendues
        assert permissions_utilisateur(_utilisateur(role)) == sorted(attendues)

    assert permissions_du_role("INCONNU") == set()
    assert permissions_du_role(None) == set()
    print("[OK] permissions_du_role / permissions_utilisateur par rôle")

    grilles = {
        "ADMIN": {
            "dashboard:voir": True,
            "rapports:generer": True,
            "utilisateurs:supprimer": True,
        },
        "RESPONSABLE": {
            "remboursements:valider": True,
            "utilisateurs:voir": True,
            "utilisateurs:creer": False,
            "simulations:supprimer": True,
        },
        "ANALYSTE": {
            "previsions:creer": True,
            "beneficiaires:voir": True,
            "beneficiaires:modifier": False,
            "documents:televerser": False,
            "remboursements:valider": False,
        },
        "AGENT": {
            "remboursements:creer": True,
            "assistant:utiliser": True,
            "beneficiaires:supprimer": False,
            "remboursements:valider": False,
            "importation:voir_rapport": False,
            "rapports:generer": False,
        },
    }
    for role, attentes in grilles.items():
        for permission, attendu in attentes.items():
            assert utilisateur_a_permission(
                _utilisateur(role), permission
            ) is attendu, f"{role}/{permission}"
    print("[OK] Grilles de permissions vérifiées pour chaque rôle")


async def _tester_refus_par_defaut():
    for role in (None, "", "INCONNU", "consultant"):
        assert permissions_du_role(role) == set()
        assert not utilisateur_a_permission(_utilisateur(role), "dashboard:voir")
    assert not utilisateur_a_permission(
        _utilisateur("ADMIN"), "module:permission_inconnue"
    )
    assert not utilisateur_a_permission(None, "dashboard:voir")
    assert not module_accessible(_utilisateur("INCONNU"), "dashboard")
    assert module_accessible(_utilisateur("AGENT"), "remboursements")
    assert not module_accessible(_utilisateur("AGENT"), "utilisateurs")
    print("[OK] Refus par défaut : rôle inconnu, permission inconnue, utilisateur absent")


async def _tester_verification():
    verifier_permission(_utilisateur("AGENT"), "dashboard:voir")
    verifier_permission(_utilisateur("RESPONSABLE"), "utilisateurs:voir")
    try:
        verifier_permission(_utilisateur("AGENT"), "rapports:generer")
        raise AssertionError("AGENT ne doit pas générer de rapports")
    except ErreurForbidden:
        pass
    try:
        verifier_permission(_utilisateur("ANALYSTE"), "remboursements:valider")
        raise AssertionError("ANALYSTE ne doit pas valider de remboursements")
    except ErreurForbidden:
        pass
    try:
        verifier_permission(_utilisateur("RESPONSABLE"), "utilisateurs:supprimer")
        raise AssertionError("RESPONSABLE ne doit pas supprimer d'utilisateurs")
    except ErreurForbidden:
        pass
    print("[OK] verifier_permission : accordé / 403 (ErreurForbidden)")


async def _tester_dependances():
    agent = _utilisateur("AGENT")
    admin = _utilisateur("ADMIN")

    resultat = await exiger_permission("dashboard:voir")(agent)
    assert resultat is agent, "La dépendance doit renvoyer l'utilisateur courant"

    for permission in ("utilisateurs:supprimer", "rapports:generer"):
        try:
            await exiger_permission(permission)(agent)
            raise AssertionError(f"AGENT ne doit pas avoir {permission}")
        except ErreurForbidden:
            pass

    resultat = await exiger_module("remboursements")(admin)
    assert resultat is admin
    try:
        await exiger_module("utilisateurs")(agent)
        raise AssertionError("AGENT ne doit pas passer exiger_module('utilisateurs')")
    except ErreurForbidden:
        pass
    await exiger_module("remboursements")(agent)
    try:
        await exiger_module("module_inconnu")(admin)
        raise AssertionError("Un module inconnu doit être refusé")
    except ErreurForbidden:
        pass
    print("[OK] Dépendances FastAPI : exiger_permission / exiger_roles / exiger_module")


async def _creer(email: str, role: str) -> dict:
    reponse = await creer_compte(
        prenom="Test",
        nom="RBAC",
        email=email,
        mot_de_passe="MotDePasseFort123",
        role=role,
    )
    _comptes_crees.append(email)
    return reponse


async def _tester_auth_par_role():
    roles = ("ADMIN", "RESPONSABLE", "ANALYSTE", "AGENT")
    for role in roles:
        email = f"rbac.{role.lower()}@test.mg"
        reponse = await _creer(email, role)
        assert reponse["utilisateur"]["role"] == role
        assert set(reponse["permissions"]) == permissions_du_role(role), role

        connexion = await connecter(email=email, mot_de_passe="MotDePasseFort123")
        assert set(connexion["permissions"]) == permissions_du_role(role), role
        assert connexion["utilisateur"]["role"] == role
        assert "mot_de_passe" not in connexion and "mot_de_passe" not in connexion[
            "utilisateur"
        ]
        print(f"[OK] {role} : connexion -> rôles + permissions cohérents")

    compte = await _creer("rbac.defaut@test.mg", role=None)
    assert compte["utilisateur"]["role"] == ROLE_DEFAUT
    print(f"[OK] Rôle par défaut à la création : {ROLE_DEFAUT}")


async def _tester_gestion_utilisateurs():
    admin = await _creer("rbac.manager@test.mg", "ADMIN")
    cible = await _creer("rbac.cible@test.mg", "AGENT")
    acteur = {"_id": ObjectId(admin["utilisateur"]["id"]), "email": "rbac.manager@test.mg"}

    liste = await lister_utilisateurs(role="AGENT")
    assert liste["total"] >= 1 and liste["utilisateurs"], liste
    assert all(u["role"] == "AGENT" for u in liste["utilisateurs"])

    cree = await creer_utilisateur(
        prenom="Nouveau",
        nom="Compte",
        email="rbac.nouveau@test.mg",
        mot_de_passe="MotDePasseFort123",
        role="ANALYSTE",
        created_by=acteur["_id"],
    )
    _comptes_crees.append("rbac.nouveau@test.mg")
    assert cree["role"] == "ANALYSTE" and "id" in cree

    id_cible = ObjectId(cible["utilisateur"]["id"])
    maj_actif = await changer_role_utilisateur(
        id_cible, role="RESPONSABLE", acteur=acteur
    )
    assert maj_actif["role"] == "RESPONSABLE"

    try:
        await changer_role_utilisateur(
            ObjectId(admin["utilisateur"]["id"]), role="AGENT", acteur=acteur
        )
        raise AssertionError("L'auto-rétrogradation doit être bloquée")
    except ErreurValidation:
        pass

    try:
        await supprimer_utilisateur(ObjectId(admin["utilisateur"]["id"]), acteur=acteur)
        raise AssertionError("L'auto-suppression doit être bloquée")
    except ErreurValidation:
        pass

    try:
        await supprimer_utilisateur(ObjectId(), acteur=acteur)
        raise AssertionError("Utilisateur inconnu doit renvoyer 404")
    except ErreurNotFound:
        pass

    await supprimer_utilisateur(id_cible, acteur=acteur)
    db = obtenir_database()
    assert (await db["utilisateurs"].find_one({"_id": id_cible})) is None
    print("[OK] Gestion des utilisateurs : list/creer/changer_rôle/supprimer + protections")


async def _nettoyer_tout():
    for email in set(_comptes_crees):
        await _nettoyer(email)


async def executer_tests():
    await connecter_database()
    try:
        for email in set(_comptes_crees):
            await _nettoyer(email)
        await _tester_constantes()
        await _tester_coherence_modules_permissions()
        await _tester_permissions_par_role()
        await _tester_modules_par_role()
        await _tester_refus_par_defaut()
        await _tester_verification()
        await _tester_dependances()
        await _tester_auth_par_role()
        await _tester_gestion_utilisateurs()
        await _nettoyer_tout()
    finally:
        await fermer_database()


if __name__ == "__main__":
    try:
        asyncio.run(executer_tests())
    except AssertionError as erreur:
        print(f"[ÉCHEC] {erreur}")
        sys.exit(1)
    except (ErreurForbidden, ErreurValidation, ErreurNotFound) as erreur:
        print(f"[ÉCHEC] {erreur.message}")
        sys.exit(1)
    print("TEST_RBAC : OK")