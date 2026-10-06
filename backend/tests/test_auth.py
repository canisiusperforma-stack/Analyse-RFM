"""Tests de l'authentification JWT.

Vérifie :
- création de compte (hashage bcrypt, mot de passe jamais en clair) ;
- unicité de l'e-mail ;
- connexion (jeton d'accès, durées d'expiration) ;
- vérification du jeton (valide, invalide, expiré) ;
- récupération de l'utilisateur connecté (/me) ;
- comptes inactifs ou inexistants refusés.

Lancement :
    python tests/test_auth.py
"""

import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bson import ObjectId

from app.config import settings
from app.database import connecter_database, fermer_database, obtenir_database
from app.security.jwt import decoder_jeton, decoder_jeton_ignorer_expiration, creer_jeton
from app.security.password import hash_mot_de_passe, verifier_mot_de_passe
from app.services.auth_service import (
    connecter,
    creer_compte,
    obtenir_utilisateur_connecte,
)
from app.utils.errors import ErreurConflict, ErreurUnauthorized, ErreurValidation

EMB = "auth.test@rfm-srb.mg"

_comptes_crees: list[str] = []
_utilisateur_test: dict = {}


async def _nettoyer(email: str) -> None:
    db = obtenir_database()
    await db["utilisateurs"].delete_many({"email": email})


async def _creer_compte_test(
    email: str = EMB,
    mot_de_passe: str = "MotDePasseFort123",
    role: str | None = None,
) -> dict:
    reponse = await creer_compte(
        prenom="Hery",
        nom="RAKOTO",
        email=email,
        mot_de_passe=mot_de_passe,
        role=role,
    )
    _comptes_crees.append(email)
    return reponse


async def _recharger_utilisateur() -> dict | None:
    db = obtenir_database()
    return await db["utilisateurs"].find_one({"email": EMB})


async def _tester_hashage():
    hash1 = hash_mot_de_passe("SuperSecret123")
    assert hash1.startswith("$2"), "Le hash doit être un hash bcrypt ($2…)"
    assert hash1 != "SuperSecret123", "Le hash ne doit jamais être le mot de passe"
    assert verifier_mot_de_passe("SuperSecret123", hash1), "doit vérifier OK"
    assert not verifier_mot_de_passe("MauvaisMotDePasse", hash1)
    assert not verifier_mot_de_passe("SuperSecret123", "")
    assert not verifier_mot_de_passe("SuperSecret123", "hash-invalide")
    hash2 = hash_mot_de_passe("SuperSecret123")
    assert hash1 != hash2, "Le sel rend chaque hash unique"
    print("[OK] Hashage bcrypt : jamais en clair, sels uniques, vérification")

    reponse = await _creer_compte_test()
    utilisateur = await _recharger_utilisateur()
    assert utilisateur is not None, "Utilisateur absent de la base"
    assert utilisateur["mot_de_passe_hash"] != "MotDePasseFort123"
    assert "MotDePasseFort123" not in utilisateur["mot_de_passe_hash"]
    assert "mot_de_passe" not in reponse["utilisateur"], (
        "Le mot de passe (même hashé) ne doit pas être renvoyé à l'API"
    )
    _utilisateur_test["_id"] = utilisateur["_id"]
    print("[OK] Conservation : seule l'empreinte bcrypt est stockée")

    jeton = reponse["access_token"]
    charge = decoder_jeton_ignorer_expiration(jeton)
    assert charge["sub"] == str(utilisateur["_id"]), charge
    assert charge.get("role") == "AGENT", charge
    assert charge.get("email") == EMB, charge
    print("[OK] Jeton : sub/role/e-mail présents dans la charge utile")


async def _tester_email_unique():
    try:
        await _creer_compte_test()
        raise AssertionError("Le doublon d'e-mail aurait dû être rejeté")
    except ErreurConflict:
        pass
    print("[OK] Unicité : e-mail déjà utilisé -> conflit")


async def _tester_connexion():
    reponse = await connecter(
        email=EMB.upper(),
        mot_de_passe="MotDePasseFort123",
    )
    assert reponse["access_token"], "Un jeton doit être émis"
    assert reponse["token_type"] == "bearer"
    assert reponse["expires_in"] > 0
    assert reponse["expires_in"] == settings.JWT_EXPIRATION_MINUTES * 60
    expire_dans = datetime.fromisoformat(reponse["expires_at"])
    assert expire_dans > datetime.now(timezone.utc), "Le jeton doit être valide"
    assert reponse["utilisateur"]["email"] == EMB
    assert "mot_de_passe" not in reponse
    print("[OK] Connexion : jeton + expiration + utilisateur (e-mail insensible à la casse)")

    try:
        await connecter(email=EMB, mot_de_passe="MauvaisMotDePasse")
        raise AssertionError("Mauvais mot de passe aurait dû être refusé")
    except ErreurUnauthorized:
        pass

    try:
        await connecter(email="inconnu@rfm-srb.mg", mot_de_passe="MotDePasseFort123")
        raise AssertionError("E-mail inconnu aurait dû être refusé")
    except ErreurUnauthorized:
        pass
    print("[OK] Refus : identifiant ou mot de passe incorrect")

    utilisateur = await _recharger_utilisateur()
    charge = decoder_jeton(reponse["access_token"])
    assert charge["sub"] == str(utilisateur["_id"]), "roundtrip jeton"
    print("[OK] Vérification du jeton : signature, exp, iss, sub")


async def _tester_jeton_expire():
    utilisateur = await _recharger_utilisateur()
    assert utilisateur is not None

    jeton_expire, _ = creer_jeton(utilisateur, expiration_minutes=-5)
    try:
        decoder_jeton(jeton_expire)
        raise AssertionError("Le jeton expiré aurait dû être rejeté")
    except ErreurUnauthorized as erreur:
        assert "expir" in erreur.message.lower(), erreur.message
    print("[OK] Expiration : jeton périmé refusé")

    try:
        decoder_jeton("jeton.pas.valide")
        raise AssertionError("Le jeton falsifié aurait dû être rejeté")
    except ErreurUnauthorized:
        pass
    print("[OK] Jeton invalide/falsifié refusé (vérification de signature)")


async def _tester_me():
    utilisateur = await _recharger_utilisateur()
    courant = await obtenir_utilisateur_connecte(_utilisateur_test.get("_id"))
    assert courant["email"] == EMB
    assert courant["_id"] == utilisateur["_id"]
    print("[OK] /me : utilisateur connecté restitué depuis le jeton")

    try:
        await obtenir_utilisateur_connecte(None)
        raise AssertionError("Absence d'identifiant aurait dû être refusée")
    except ErreurUnauthorized:
        pass

    try:
        await obtenir_utilisateur_connecte(ObjectId())
        raise AssertionError("Utilisateur inexistant aurait dû être refusé")
    except ErreurUnauthorized:
        pass
    print("[OK] /me : jeton absent / utilisateur introuvable -> 401")


async def _tester_compte_inactif():
    db = obtenir_database()
    utilisateur = await _recharger_utilisateur()
    await db["utilisateurs"].update_one(
        {"_id": utilisateur["_id"]},
        {"$set": {"actif": False}},
    )
    try:
        await connecter(email=EMB, mot_de_passe="MotDePasseFort123")
        raise AssertionError("Compte désactivé aurait dû être refusé")
    except ErreurUnauthorized as erreur:
        assert "désactivé" in erreur.message.lower(), erreur.message
    try:
        await obtenir_utilisateur_connecte(utilisateur["_id"])
        raise AssertionError("Compte inactif aurait dû être refusé")
    except ErreurUnauthorized:
        pass
    await db["utilisateurs"].update_one(
        {"_id": utilisateur["_id"]},
        {"$set": {"actif": True}},
    )
    print("[OK] Compte désactivé refusé à la connexion et au /me")


async def _tester_role_creation():
    reponse = await _creer_compte_test(
        email="role.validateur@rfm-srb.mg",
        role="RESPONSABLE",
    )
    assert reponse["utilisateur"]["role"] == "RESPONSABLE"

    try:
        await _creer_compte_test(
            email="role.invalide@rfm-srb.mg",
            role="superadmin",
        )
        raise AssertionError("Rôle invalide aurait dû être refusé")
    except ErreurValidation:
        pass
    await _nettoyer("role.invalide@rfm-srb.mg")
    print("[OK] Rôles contrôlés à la création ; rôle valide accepté")


async def _nettoyer_tout():
    for email in set(_comptes_crees):
        await _nettoyer(email)
    print("[OK] Nettoyage des comptes de test")


async def executer_tests():
    await connecter_database()
    try:
        for email in (
            EMB,
            "role.validateur@rfm-srb.mg",
            "role.invalide@rfm-srb.mg",
        ):
            await _nettoyer(email)
        await _tester_hashage()
        await _tester_email_unique()
        await _tester_connexion()
        await _tester_jeton_expire()
        await _tester_me()
        await _tester_compte_inactif()
        await _tester_role_creation()
        await _nettoyer_tout()
    finally:
        await fermer_database()


if __name__ == "__main__":
    try:
        asyncio.run(executer_tests())
    except AssertionError as erreur:
        print(f"[ÉCHEC] {erreur}")
        sys.exit(1)
    except (ErreurUnauthorized, ErreurConflict, ErreurValidation) as erreur:
        print(f"[ÉCHEC] {erreur.message}")
        sys.exit(1)
    print("TEST_AUTH : OK")