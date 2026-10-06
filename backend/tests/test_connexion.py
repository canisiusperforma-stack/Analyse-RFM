"""Test de connexion FastAPI -> MongoDB.

Vérifie la couche `app.database` :
- connexion asynchrone via Motor ;
- vérification de connexion (ping) ;
- fermeture propre et idempotente ;
- gestion des erreurs après fermeture.

Lancement :
    python tests/test_connexion.py
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings
from app.database import (
    ErreurConnexionDatabase,
    connecter_database,
    etat_base_donnees,
    fermer_database,
    obtenir_client,
    obtenir_database,
    verifier_connexion_mongodb,
)


async def tester_configuration() -> None:
    assert settings.MONGODB_URL.startswith("mongodb://"), "MONGODB_URL invalide"
    assert settings.MONGODB_DATABASE == "rfm_srb_vatovavy", (
        f"MONGODB_DATABASE inattendu : {settings.MONGODB_DATABASE}"
    )
    print(f"[OK] Configuration : {settings.MONGODB_DATABASE} via {settings.MONGODB_URL}")


async def tester_connexion() -> None:
    base = await connecter_database()
    assert base is not None, "La base renvoyée ne doit pas être None"
    assert base.name == settings.MONGODB_DATABASE, (
        f"Nom de base inattendu : {base.name}"
    )
    assert await connecter_database() is base, (
        "connecter_database() doit être idempotente"
    )
    assert etat_base_donnees()["connecte"] is True, "L'état doit être connecté"
    print(f"[OK] Connexion établie : '{base.name}'")


async def tester_verification() -> None:
    assert await verifier_connexion_mongodb() is True, "Le ping doit renvoyer True"
    client = obtenir_client()
    assert client is not None, "Le client ne doit pas être None"
    print("[OK] Vérification de connexion : ping réussi")


async def tester_fermeture() -> None:
    base_avant = await connecter_database()
    await fermer_database()
    await fermer_database()
    assert etat_base_donnees()["connecte"] is False, (
        "L'état doit être déconnecté après fermeture"
    )
    for accesseur in (obtenir_client, obtenir_database):
        try:
            accesseur()
        except ErreurConnexionDatabase:
            continue
        raise AssertionError(f"{accesseur.__name__}() aurait dû lever une erreur")
    reprise = await connecter_database()
    assert reprise is not None and reprise.name == settings.MONGODB_DATABASE, (
        "La reconnexion après fermeture doit fonctionner"
    )
    await fermer_database()
    print("[OK] Fermeture propre, idempotente et reconnexion réussies")


async def executer_tests() -> None:
    await tester_configuration()
    await tester_connexion()
    await tester_verification()
    await tester_fermeture()


if __name__ == "__main__":
    try:
        asyncio.run(executer_tests())
    except AssertionError as erreur:
        print(f"[ÉCHEC] {erreur}")
        sys.exit(1)
    except ErreurConnexionDatabase as erreur:
        print(f"[ÉCHEC] Connexion MongoDB impossible : {erreur}")
        sys.exit(1)
    print("TEST_CONNEXION : OK")