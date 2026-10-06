from app.database.connection import connecter_database, obtenir_client


async def verifier_connexion_mongodb() -> bool:
    """Vérifie que la connexion à MongoDB est opérationnelle (ping)."""
    await connecter_database()
    client = obtenir_client()
    await client.admin.command("ping")
    return True