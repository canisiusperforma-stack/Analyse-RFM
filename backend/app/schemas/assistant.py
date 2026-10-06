"""Schémas de l'assistant conversationnel.

Ce module décrit deux choses : le **contrat d'entrée** de
`POST /assistant/question` et de `POST /assistant/query`, et le **contrat de
sortie** de l'orchestration.

L'absence historique de schéma de sortie était un choix assumé : la réponse du
pipeline DATA est un compte rendu d'exécution dont la forme dépend du chemin
parcouru. Ce choix ne vaut plus dès lors que quatre chemins cohabitent (DATA,
RAG, DATA_RAG, hors périmètre) : sans contrat déclaré, deux champs homonymes
signifieraient deux choses différentes selon l'itération. D'où
`ReponseAssistant`, qui **impose** la présence des quatre blocs — question,
route, contenu, provenance — tout en gardant le champ `resultat` brut pour
l'audit, et qui interdit (`extra="forbid"`) tout champ que le backend ne
produirait pas.

Séparation des deux vocabulaires
    `sources` et `documents` ne sont pas synonymes, et la confusion serait
    coûteuse :

    - `sources` décrit **ce que le backend a interrogé pour calculer** —
      fonction, module, exercice. C'est la provenance du chiffre.
- `documents` décrit **les extraits de documents autorisés** qui ont été
      trouvés et peuvent être cités — nom de fichier, page, extrait.

    Un chiffre n'a pas de source documentaire ; une citation n'a pas de module
    fournisseur. Les séparer rend impossible, par construction, d'attribuer un
    chiffre à un document qui ne l'a pas produit.

Les bornes reprennent celles de la configuration (`settings.LLM_QUESTION_MAX`,
`settings.LLM_TOURS_HISTORIQUE`) et non des valeurs en dur, afin que le contrat
HTTP et le traitement interne ne puissent pas diverger.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.config import settings

RoleTour = Literal["user", "assistant"]

#: Chemins possibles d'une question. `INCONNUE` est un chemin à part entière et
#: non une erreur : aucune source n'est interrogée, la réponse est une
#: explication de périmètre.
IntentRoute = Literal["DATA", "RAG", "DATA_RAG", "INCONNUE"]


class TourConversation(BaseModel):
    """Un tour de l'historique, rejoué devant le modèle.

    L'historique n'apporte que la continuité de la conversation. Il n'est
    jamais une source de chiffres : `app.ai.prompt_manager` le rappelle
    explicitement au modèle, dont chaque valeur est sinon rapprochée du
    résultat calculé par `app.ai.response_validator`.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    role: RoleTour = Field(
        description="Auteur du tour : l'utilisateur ou l'assistant.",
    )
    content: str = Field(
        min_length=1,
        max_length=2000,
        description="Texte du tour, tronqué côté service si l'historique déborde.",
    )


class QuestionAssistant(BaseModel):
    """Corps de la requête « poser une question ».

    Le champ `exercice` permet de forcer la période lorsque la question ne la
    nomme pas. À `null`, chaque indicateur applique la règle du service qui le
    fournit : le plus récent exercice disponible.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    question: str = Field(
        min_length=1,
        max_length=settings.LLM_QUESTION_MAX,
        description=(
            "Question en langage naturel, par exemple « Quel est le taux "
            "d'exécution du budget RFM ? »."
        ),
        examples=["Quel est le taux d'exécution du budget RFM ?"],
    )
    exercice: int | None = Field(
        default=None,
        ge=1900,
        le=2100,
        description=(
            "Exercice imposé (défaut : le plus récent disponible pour "
            "l'indicateur retenu)."
        ),
        examples=[2025],
    )
    historique: list[TourConversation] = Field(
        default_factory=list,
        max_length=settings.LLM_TOURS_HISTORIQUE * 2,
        description="Tours précédents, pour la continuité de conversation.",
    )


class QuestionOrchestration(BaseModel):
    """Corps de la requête « orchestrer une question ».

    Même contrat d'entrée que `QuestionAssistant`, avec deux extensions :

    - `documents` restreint la recherche documentaire à un sous-ensemble de
      documents. Ce périmètre est **combiné** à la clause d'accès, jamais
      substitué à elle : un document listé ici mais non autorisé par son rôle
      reste inaccessible.
    - `exercice` joue un rôle différent de celui du chemin DATA. Il y force la
      période ; ailleurs, il **lève l'ambiguïté**. Sans lui, une question
      dépourvue d'année (« Quel est le taux d'exécution ? ») reçoit une demande
      de précision au lieu d'être répondue sur un exercice arbitraire.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    question: str = Field(
        min_length=1,
        max_length=settings.LLM_QUESTION_MAX,
        description="Question en langage naturel.",
        examples=["Le niveau d'exécution observé respecte-t-il les règles ?"],
    )
    exercice: int | None = Field(
        default=None,
        ge=1900,
        le=2100,
        description="Exercice imposé, ou période levée par l'appelant.",
    )
    documents: list[str] = Field(
        default_factory=list,
        max_length=50,
        description="Identifiants de documents à consulter (sous-ensemble).",
    )
    historique: list[TourConversation] = Field(
        default_factory=list,
        max_length=settings.LLM_TOURS_HISTORIQUE * 2,
        description="Tours précédents, pour la continuité de conversation.",
    )


# --- Routage ----------------------------------------------------------------


class RouteQuery(BaseModel):
    """Décision du routeur : quel chemin minimal emprunter, et sur quoi.

    C'est le schéma qui rend le routage **auditable**. Un routeur qui se
    contente de renvoyer une étiquette libre ne permettrait ni de savoir quel
    indicateur a été visé, ni de vérifier qu'une période arbitraire n'a pas été
    choisie. Chaque champ existe pour une raison vérifiable :

    - `intent` — le chemin effectivement emprunté ;
    - `requiert_donnees` / `requiert_documents` — ce que l'orchestrateur doit
      interroger, déduits de `intent` et non Lus indépendamment ;
    - `confiance` — issue du rapport entre l'indice gagnant et le total, donc
      un nombre de comparable à celui du validateur numérique ;
    - `besoin_clarification` — signal explicite qu'aucune période n'a pu être
      déduite, pour que l'orchestrateur demande au lieu de choisir.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    question: str = Field(description="Question telle que reçue.")
    intent: IntentRoute = Field(
        description="Chemin minimal emprunté par l'orchestrateur.",
    )
    indicateur: str | None = Field(
        default=None,
        description="Code de l'indicateur visé par la partie données.",
    )
    libelle_indicateur: str | None = Field(
        default=None,
        description="Libellé lisible de cet indicateur.",
    )
    periode: int | None = Field(
        default=None,
        description="Exercice retenu, uniquement s'il est explicite dans la "
        "question ou imposé par l'appelant.",
    )
    categorie: str | None = Field(
        default=None,
        description="Catégorie statistique visée, lorsqu'elle est identifiable.",
    )
    type_analyse: str | None = Field(
        default=None,
        description="Nature du calcul demandé (total, extremum, comparaison).",
    )
    requiert_donnees: bool = Field(
        description="Interroger la base de données (MongoDB).",
    )
    requiert_documents: bool = Field(
        description="Interroger la base documentaire (vector store).",
    )
    confiance: float = Field(
        ge=0.0,
        le=1.0,
        description="Confiance du routeur, de 0 à 1.",
    )
    raison: str = Field(
        description="Justification en une phrase, tracée dans les logs.",
    )
    scores: dict[str, float] = Field(
        default_factory=dict,
        description="Indices calculés par source, pour audit.",
    )
    besoin_clarification: bool = Field(
        default=False,
        description="Une période est nécessaire et n'a pas pu être déduite.",
    )
    question_clarification: str | None = Field(
        default=None,
        description="Précision à demander à l'utilisateur.",
    )
    parametres_manquants: list[str] = Field(
        default_factory=list,
        description="Paramètres requis mais non déductibles de la question.",
    )
    indices_documentaires: list[str] = Field(
        default_factory=list,
        description="Termes documentaires reconnus dans la question.",
    )

    @field_validator("requiert_documents")
    @classmethod
    def _verifier_coherence_chemin(cls, valeur: bool, info) -> bool:
        """Empêche un chemin qui n'interroge aucune source.

        Une incohérence entre `intent` et les deux indicateurs de besoin
        produirait une requête inutile — précisément ce que le routeur doit
        éviter. La validation la fait échouer ici plutôt que de la laisser
        atteindre MongoDB.

        Le contrôle porte sur `requiert_documents`, déclaré après
        `requiert_donnees` : les deux sont alors disponibles dans `info.data`.
        C'est le seul emplacement où le couple peut être vérifié, et cela évite
        d'avoir à dupliquer la règle en deux validateurs partiels.
        """
        intent = info.data.get("intent")
        donnees = bool(info.data.get("requiert_donnees"))
        attendu = {
            "DATA": (True, False),
            "RAG": (False, True),
            "DATA_RAG": (True, True),
            "INCONNUE": (False, False),
        }.get(intent)
        if attendu is None:
            raise ValueError(f"Chemin inconnu : {intent!r}")
        if (donnees, valeur) != attendu:
            raise ValueError(
                f"Le chemin {intent} exige (données, documents) = {attendu}, "
                f"reçu ({donnees}, {valeur})."
            )
        return valeur


# --- Contexte structuré (§7 du cahier des charges) --------------------------


class MesureContexte(BaseModel):
    """Une valeur calculée, déjà formatée, telle que le modèle la verra."""

    model_config = ConfigDict(extra="forbid")

    cle: str
    libelle: str
    valeur: Any
    unite: str
    valeur_affichee: str = Field(
        description="Rendu canonique ; le validateur le reconnaît verbatim.",
    )


class ContexteDonnees(BaseModel):
    """Bloc « chiffres observés » : résultat structuré du calcul backend."""

    model_config = ConfigDict(extra="forbid")

    indicateur: str
    libelle: str
    periode: int | None = None
    statut: str = Field(description="disponible, partiel ou absent.")
    valeur_principale: Any = None
    unite: str | None = None
    calcul: str | None = Field(
        default=None,
        description="Formule et origine du calcul, produites par le code.",
    )
    source: str = Field(
        default="MongoDB",
        description="Origine des valeurs : jamais le modèle.",
    )
    source_detail: list[dict[str, Any]] = Field(default_factory=list)
    mesures: list[MesureContexte] = Field(default_factory=list)
    tableau: dict[str, Any] | None = None
    absence: str | None = Field(
        default=None,
        description="Motif exact de l'indisponibilité, s'il y en a une.",
    )


class ContexteDocument(BaseModel):
    """Bloc « règles documentaires » : un extrait autorisé et citable."""

    model_config = ConfigDict(extra="forbid")

    etiquette: str = Field(description="Marqueur de citation, par exemple S1.")
    document: str = Field(description="Nom du fichier d'origine.")
    document_id: str | None = None
    page: int | None = None
    reference: str | None = None
    titre: str | None = None
    confidentialite: str | None = None
    score: float = 0.0
    extrait: str


class ContexteAssistant(BaseModel):
    """Contexte unique transmis au modèle, toutes sources confondues.

    C'est **le seul** objet que le modèle reçoit. Il ne dispose d'aucun accès
    à MongoDB, ni aux collections, ni aux index vectoriels : il ne peut donc
    pas élargir ce qu'il voit, seulement reformuler ce qu'il lui est donné.

    La séparation en deux blocs n'est pas décorative. Elle impose au modèle —
    et permet à `response_validator` de vérifier ensuite — que les chiffres
    viennent du premier bloc et les règles du second, sans les mélanger.
    """

    model_config = ConfigDict(extra="forbid")

    question: str
    intent: IntentRoute
    data_context: ContexteDonnees | None = None
    document_context: list[ContexteDocument] = Field(default_factory=list)
    limites: list[str] = Field(
        default_factory=list,
        description="Limites que la réponse doit signaler.",
    )


# --- Réponse d'orchestration (§13) -----------------------------------------


class DocumentCite(BaseModel):
    """Extrait documentaire effectivement utilisé dans la réponse."""

    model_config = ConfigDict(extra="forbid")

    etiquette: str
    document: str
    document_id: str | None = None
    page: int | None = None
    reference: str | None = None
    titre: str | None = None
    confidentialite: str | None = None
    score: float = 0.0
    cite: bool = False
    extrait: str


class ReponseAssistant(BaseModel):
    """Contrat de sortie de `POST /assistant/query`.

    Les quatre blocs demandés — `data`, `documents`, `sources`, `confidence` —
    sont tous présents, y compris quand ils sont vides : l'absence est une
    information, et un champ omis la ferait disparaître. `intent` rend le
    chemin emprunté explicite sans que l'utilisateur ait à le déduire du
    contenu.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    question: str
    intent: IntentRoute
    reponse: str = Field(description="Réponse naturelle, en français.")
    data: ContexteDonnees | None = Field(
        default=None,
        description="Bloc données. Absent pour une question purement "
        "documentaire ou hors périmètre.",
    )
    documents: list[DocumentCite] = Field(
        default_factory=list,
        description="Extraits de documents autorisés utilisés.",
    )
    sources: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Provenance du calcul : fonction, module, exercice.",
    )
    confidence: float = Field(ge=0.0, le=1.0)
    exercice: int | None = None
    analyse: dict[str, Any] = Field(
        default_factory=dict,
        description="Décision du routeur, pour audit.",
    )
    resultat: dict[str, Any] = Field(
        default_factory=dict,
        description="Résultat structuré brut, pour audit.",
    )
    controle: dict[str, Any] = Field(
        default_factory=dict,
        description="Verdict du validateur : chiffres, citations, documents.",
    )
    generee_par: Literal["llm", "backend"] = Field(
        description="Auteur de la réponse rendu à l'utilisateur.",
    )
    modele: str | None = None
    regle: str = Field(description="Règle d'exactitude appliquée.")
    avertissements: list[str] = Field(default_factory=list)
    limites: list[str] = Field(default_factory=list)
    clarification: dict[str, Any] | None = Field(
        default=None,
        description="Précision demandée à l'utilisateur, s'il en faut une.",
    )
    hors_perimetre: bool = False
    reponse_rejetee: str | None = Field(
        default=None,
        description="Réponse écartée du modèle, pour diagnostic.",
    )
    duree_ms: int = 0
    chemin: list[str] = Field(
        default_factory=list,
        description="Services réellement sollicités, dans l'ordre.",
    )
