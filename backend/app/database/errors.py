class ErreurConnexionDatabase(Exception):
    """Erreur levée lorsque la connexion à MongoDB n'est pas disponible."""

    def __init__(self, message: str = "Connexion à MongoDB indisponible") -> None:
        self.message = message
        super().__init__(message)