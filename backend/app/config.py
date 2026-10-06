from functools import lru_cache
from pathlib import Path
from typing import List

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    APP_NAME: str = "Plateforme RFM SRB Vatovavy"
    APP_DESCRIPTION: str = (
        "API d'analyse, de prévision et d'aide à la décision du RFM"
    )
    APP_VERSION: str = "1.0.0"
    APP_ENV: str = "development"
    DEBUG: bool = True

    API_HOST: str = "127.0.0.1"
    API_PORT: int = 8000

    CORS_ORIGINS: str = (
        "http://localhost:5173,http://127.0.0.1:5173,"
        "http://localhost:3000,http://127.0.0.1:3000"
    )
    CORS_ALLOW_CREDENTIALS: bool = True
    CORS_ALLOW_METHODS: str = "*"
    CORS_ALLOW_HEADERS: str = "*"

    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = (
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    )
    LOG_FILE: str = str(BASE_DIR / "logs" / "app.log")

    MONGODB_URL: str = "mongodb://127.0.0.1:27017"
    MONGODB_DATABASE: str = "rfm_srb_vatovavy"

    JWT_SECRET: str = "dev-secret-a-changer-absolument-en-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRATION_MINUTES: int = 60
    JWT_ISSUER: str = "rfm-srb-vatovavy"

    LLM_ENABLED: bool = False
    LLM_BASE_URL: str = "http://127.0.0.1:11434/v1"
    LLM_API_KEY: str = ""
    LLM_MODELE: str = "llama3.1"
    LLM_TEMPERATURE: float = 0.0
    LLM_TOKENS_MAX: int = 900
    LLM_DELAI_MAX: int = 60
    LLM_TOURS_HISTORIQUE: int = 4
    LLM_QUESTION_MAX: int = 500
    LLM_TOLERANCE_NUMERIQUE: float = 0.01
    LLM_SOURCES_MAX: int = 12

    RAG_ENABLED: bool = False
    RAG_EXTENSIONS: str = "pdf,txt,md,csv,json,xlsx"
    RAG_TAILLE_MAX_OCTETS: int = 20 * 1024 * 1024
    RAG_CHUNK_TAILLE: int = 900
    RAG_CHUNK_TAILLE_MIN: int = 180
    RAG_CHUNK_RECOUVREMENT: int = 150
    RAG_EMBED_DIM: int = 2048
    RAG_EMBED_MODELE: str = "local-hash"
    RAG_RECHERCHE_TOP_K: int = 6
    RAG_RECHERCHE_CANDIDATS: int = 200
    RAG_CONTEXTE_CARACTERES_MAX: int = 12000
    RAG_SEUIL_PERTINENCE: float = 0.25
    RAG_PONDERATION_DENSE: float = 0.7
    RAG_CITATIONS_EXIGEES: bool = True
    RAG_TEMPERATURE: float = 0.0
    RAG_TOKENS_MAX: int = 900
    RAG_HISTORIQUE_TOURS: int = 4
    RAG_QUESTION_MAX: int = 500
    RAG_EXTRACTION_AUTO: bool = True
    RAG_SOURCES_MIN: int = 1

    # --- Orchestration IA (routeur DATA / RAG / DATA_RAG) -------------------
    #
    # Ces réglages ne pilotent ni le modèle ni la recherche : ils bornent le
    # **routeur** (`app.ai.query_router`), qui décide du chemin minimal à
    # emprunter. Leur rôle est d'éviter deux fautes symétriques : interroger la
    # base documentaire pour une question purement chiffrée, ou refuser la
    # recherche documentaire sur une question qui porte explicitement sur les
    # documents.
    #
    # Les seuils sont volontairement **disjoints** : la présence d'un motif
    # documentaire ne suffit pas à basculer en RAG, il faut que l'indice
    # documentaire dépasse son seuil tout en gardant un indice de données
    # exploitable. Une mention isolée — « le solde global est-il conforme ? » —
    # reste ainsi une question de données.

    ASSISTANT_FUSION_ENABLED: bool = True
    ASSISTANT_ROUTEUR_SEUIL_RAG: float = 0.34
    ASSISTANT_ROUTEUR_SEUIL_DATA: float = 0.30
    ASSISTANT_CLARIFICATION: bool = True
    ASSISTANT_RAG_SEUIL: float | None = None
    ASSISTANT_RAG_TOP_K: int = 4

    @field_validator("ASSISTANT_RAG_SEUIL", mode="before")
    @classmethod
    def _absent_si_vide(cls, valeur):
        """Traite une valeur vide comme une absence de surcharge.

        Un fichier `.env` ne peut pas écrire « null » : la ligne se déclare
        `ASSISTANT_RAG_SEUIL=`, et pydantic y lirait une chaîne vide. La
        traiter comme `None` permet de garder dans le modèle d'environnement
        une ligne visible — et donc lisible par l'administrateur — sans
        contraindre à la fois de la renseigner et de la supprimer.
        """
        if valeur is None:
            return None
        if isinstance(valeur, str) and not valeur.strip():
            return None
        return valeur

    @model_validator(mode="after")
    def _verifier_coherence_rag(self):
        if self.RAG_EMBED_DIM < 64:
            raise ValueError(
                "RAG_EMBED_DIM doit être d'au moins 64 dimensions."
            )
        if not 0.0 <= self.RAG_PONDERATION_DENSE <= 1.0:
            raise ValueError(
                "RAG_PONDERATION_DENSE doit être compris entre 0 et 1."
            )
        if self.RAG_RECHERCHE_TOP_K < 1:
            raise ValueError("RAG_RECHERCHE_TOP_K doit être au moins 1.")
        if self.RAG_CHUNK_TAILLE_MIN >= self.RAG_CHUNK_TAILLE:
            raise ValueError(
                "RAG_CHUNK_TAILLE_MIN doit être inférieur à RAG_CHUNK_TAILLE."
            )
        if self.RAG_CHUNK_RECOUVREMENT >= self.RAG_CHUNK_TAILLE:
            raise ValueError(
                "RAG_CHUNK_RECOUVREMENT doit être inférieur à RAG_CHUNK_TAILLE."
            )
        if not 0.0 <= self.RAG_SEUIL_PERTINENCE < 1.0:
            raise ValueError(
                "RAG_SEUIL_PERTINENCE doit être compris entre 0 (inclus) et 1."
            )
        return self

    @model_validator(mode="after")
    def _verifier_coherence_routeur(self):
        # Les deux seuils du routeur doivent rester distincts : un seuil égal
        # rendrait la frontière DATA / DATA_RAG ambiguë, et le routeur
        # trancherait alors au hasard selon l'ordre de résolution des motifs.
        if not 0.0 <= self.ASSISTANT_ROUTEUR_SEUIL_RAG <= 1.0:
            raise ValueError(
                "ASSISTANT_ROUTEUR_SEUIL_RAG doit être compris entre 0 et 1."
            )
        if not 0.0 <= self.ASSISTANT_ROUTEUR_SEUIL_DATA <= 1.0:
            raise ValueError(
                "ASSISTANT_ROUTEUR_SEUIL_DATA doit être compris entre 0 et 1."
            )
        if self.ASSISTANT_RAG_SEUIL is not None and not 0.0 <= (
            self.ASSISTANT_RAG_SEUIL
        ) <= 1.0:
            raise ValueError(
                "ASSISTANT_RAG_SEUIL doit être compris entre 0 et 1, ou absent."
            )
        if self.ASSISTANT_RAG_TOP_K < 1:
            raise ValueError("ASSISTANT_RAG_TOP_K doit être au moins 1.")
        return self

    @model_validator(mode="after")
    def _verifier_securite_llm(self):
        if self.APP_ENV == "production" and self.LLM_ENABLED:
            if not self.LLM_BASE_URL.startswith("https://"):
                raise ValueError(
                    "LLM_BASE_URL doit être en HTTPS en environnement de production."
                )
            if not self.LLM_API_KEY:
                raise ValueError(
                    "LLM_API_KEY doit être défini lorsque le LLM est activé "
                    "en environnement de production."
                )
        return self

    @model_validator(mode="after")
    def _verifier_secret_jwt_en_production(self):
        if (
            self.APP_ENV == "production"
            and self.JWT_SECRET
            == "dev-secret-a-changer-absolument-en-production"
        ):
            raise ValueError(
                "JWT_SECRET doit être défini (valeur distincte du défaut) "
                "en environnement de production."
            )
        return self

    @property
    def seuil_rag_assistant(self) -> float:
        """Seuil de pertinence documentaire appliqué par l'assistant.

        `None` signifie « hériter du seuil du module RAG ». La surcharge existe
        pour les questions de fusion, dont la formulation est plus riche que
        celle d'une recherche documentaire : « le taux d'exécution respecte-t-il
        les règles ? » partage peu de mots avec la procédure cherchée, et le
        seuil générique risquerait de la laisser à tort sans source.
        """
        if self.ASSISTANT_RAG_SEUIL is not None:
            return float(self.ASSISTANT_RAG_SEUIL)
        return float(self.RAG_SEUIL_PERTINENCE)

    @property
    def rag_extensions(self) -> List[str]:
        return [
            extension.strip().lower().lstrip(".")
            for extension in self.RAG_EXTENSIONS.split(",")
            if extension.strip()
        ]

    @property
    def cors_origins(self) -> List[str]:
        return [
            origine.strip()
            for origine in self.CORS_ORIGINS.split(",")
            if origine.strip()
        ]

    @property
    def cors_allow_methods(self) -> List[str]:
        return [
            methode.strip()
            for methode in self.CORS_ALLOW_METHODS.split(",")
            if methode.strip()
        ]

    @property
    def cors_allow_headers(self) -> List[str]:
        return [
            entete.strip()
            for entete in self.CORS_ALLOW_HEADERS.split(",")
            if entete.strip()
        ]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()