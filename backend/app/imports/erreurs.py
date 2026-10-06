class ErreurImportation(Exception):
    """Erreur levée lors du traitement d'un fichier d'importation."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)