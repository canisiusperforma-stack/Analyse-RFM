class ErreurDocumentaire(Exception):
    """Erreur levée lors du traitement d'un document de la base documentaire.

    Elle couvre l'extraction, le nettoyage, le découpage et l'indexation. Elle est
    distincte de `ErreurValidation` (contrat HTTP) parce qu'elle décrit un
    échec de pipeline, imputable au fichier déposé, et non une requête
    mal formée : la route la traduit en `422`.
    """

    def __init__(self, message: str, etapa: str | None = None) -> None:
        self.message = message
        self.etape = etapa
        super().__init__(message)
