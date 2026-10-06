"""Pipeline RAG documentaire.

Le package est organisé dans l'ordre exact où le besoin le décrit :
`document_loader` (extraction), `text_splitter` (nettoyage et découpage),
`embeddings` (vectorisation), `vector_store` (recherche), `retriever`
(recherche et contexte), `prompt_builder` (contexte remis au modèle),
`grounding` (contrôle de la réponse), `rag_service` (orchestration).

Seul `rag_service` est destiné aux appelants : il expose l'indexation, la
recherche et la réponse, et garantit les deux règles du besoin — le modèle n'est
pas appelé sans source, et une réponse non fondée n'est pas renvoyée. Les autres
modules sont importés directement lorsqu'un besoin de granularité l'impose, par
exemple pour le référentiel de l'API ou les tests.
"""

from app.rag.erreurs import ErreurDocumentaire
from app.rag.rag_service import (
    MESSAGE_ABSENCE,
    ReponseRAG,
    ResultatIndexation,
    indexer,
    repondre,
    rechercher,
)

__all__ = [
    "ErreurDocumentaire",
    "MESSAGE_ABSENCE",
    "ReponseRAG",
    "ResultatIndexation",
    "indexer",
    "repondre",
    "rechercher",
]
