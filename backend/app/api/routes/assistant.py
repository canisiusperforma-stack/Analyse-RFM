"""Routes Assistant : questions en langage naturel sur les données RFM.

Le traitement d'une question est entièrement délégué à
`app.ai.assistant_service`, qui enchaîne les huit étapes imposées :

    question utilisateur → analyse → identification de l'indicateur →
    requête backend → calcul exact → résultat structuré → modèle de langage →
    explication naturelle contrôlée

Aucune de ces étapes ne vit dans cette couche : la route se contente de
valider l'entrée, d'appliquer le contrôle d'accès et de renvoyer le compte
rendu d'exécution. C'est ce qui permet d'auditer la règle fondamentale — le
modèle ne calcule ni ne choisit aucune valeur — sans passer par le code HTTP.

Les valeurs de `exercice` sont des `int` : `budget_service` et
`remboursement_service` les convertissent en `datetime` pour borner les
requêtes, ce qui échouerait sur une chaîne.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from app.ai import assistant_service, llm_service, query_router
from app.schemas.assistant import (
    QuestionAssistant,
    QuestionOrchestration,
    ReponseAssistant,
)
from app.security.permissions import exiger_permission
from app.services import budget_service, beneficiaires_service, remboursement_service
from app.utils.errors import ErreurInterne
from app.utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter()

_PERMISSION_ASSISTANT = "assistant:utiliser"


async def _exercices_disponibles() -> list[int]:
    """Exercices présents dans au moins une source de données.

    L'union des trois sources est retenue plutôt que leur intersection : un
    exercice peut alimenter la population sans alimenter encore le budget. Le
    choix de la source revient à chaque indicateur, et une source muette sur un
    exercice se traduit alors par une réponse « donnée absente », jamais par un
    zéro. Une exception d'un service est ignorée pour ne pas priver
    l'utilisateur des exercices qu'un autre service connaît.
    """
    sources = (
        budget_service.exercices_budgetaires,
        beneficiaires_service.exercices_population,
        remboursement_service.exercices_remboursements,
    )

    exercices: set[int] = set()
    for source in sources:
        try:
            exercices.update(int(annee) for annee in await source())
        except Exception as erreur:  # noqa: BLE001
            logger.warning(
                "Exercices indisponibles via %s : %s", source.__module__, erreur
            )

    return sorted(exercices, reverse=True)


@router.post(
    "/question",
    summary="Poser une question sur les données RFM",
    description=(
        "Traite une question en langage naturel selon le pipeline imposé : "
        "analyse, identification de l'indicateur, requête backend, calcul "
        "exact, résultat structuré, puis rédaction par le modèle de langage.\n\n"
        "**Aucun chiffre n'est produit par le modèle.** Chaque valeur annoncée "
        "a été calculée par le backend avant toute génération, puis rapprochée "
        "du résultat structuré ; une valeur non rattachée fait rejeter la "
        "réponse au profit d'une rédaction produite par le code. Si les "
        "données nécessaires sont absentes, le modèle n'est pas appelé et la "
        "réponse nomme explicitement ce qui manque.\n\n"
        "La réponse renvoie le texte, l'analyse de la question, le résultat "
        "structuré, les sources interrogées, le verdict du contrôle numérique "
        "et la provenance (`generee_par` : `llm` ou `backend`)."
    ),
    response_description="Compte rendu d'exécution du pipeline et réponse rédigée.",
)
async def poser_question(
    requete: QuestionAssistant,
    utilisateur: dict = Depends(exiger_permission(_PERMISSION_ASSISTANT)),
) -> dict[str, Any]:
    return await assistant_service.repondre(
        question=requete.question,
        utilisateur=utilisateur,
        historique=[tour.model_dump() for tour in requete.historique],
        exercice=requete.exercice,
    )


@router.post(
    "/query",
    summary="Poser une question combinant données RFM et documents SRB",
    description=(
        "Orchestre une question vers le chemin minimal qu'elle appelle : "
        "`DATA` (calcul RFM), `RAG` (documents), `DATA_RAG` (rapprochement) ou "
        "`INCONNUE` (hors périmètre).\n\n"
        "Le chemin est décidé par le code, jamais par un modèle de langage, et "
        "aucune source n'est interrogée avant que cette décision soit prise. "
        "Une question dont la période manque reçoit une demande de précision "
        "sans qu'aucune requête ne parte.\n\n"
        "**Les deux provenances restent distinctes jusqu'au bout.** `sources` "
        "décrit ce que le backend a interrogé pour calculer ; `documents` décrit "
        "les extraits autorisés qui peuvent être cités. Un chiffre n'a pas de "
        "source documentaire, une citation n'a pas de module fournisseur.\n\n"
        "Chaque valeur annoncée est rapprochée de l'index des valeurs autorisées "
        "— issues du calcul **et** des extraits — et chaque marqueur de citation "
        "est vérifié. Une réponse non conforme est remplacée par un texte "
        "produit par le backend, et `generee_par` vaut alors `backend`.\n\n"
        "Un canal indisponible n'annule pas l'autre : la partie accessible est "
        "servie, la partie refusée est énoncée dans `limites`."
    ),
    response_model=ReponseAssistant,
    response_description="Réponse d'orchestration et ses provenances.",
)
async def poser_requete(
    requete: QuestionOrchestration,
    utilisateur: dict = Depends(exiger_permission(_PERMISSION_ASSISTANT)),
) -> dict[str, Any]:
    return await assistant_service.orchestrer(
        question=requete.question,
        utilisateur=utilisateur,
        historique=[tour.model_dump() for tour in requete.historique],
        exercice=requete.exercice,
        documents=requete.documents,
    )


@router.get(
    "/routes",
    summary="Chemins de routage disponibles",
    description=(
        "Chemins que l'orchestrateur peut emprunter, les services que chacun "
        "sollicite, les seuils appliqués et l'état de la fusion.\n\n"
        "Expose la *forme* du routage, non ses tables de motifs : l'interface "
        "a besoin d'expliquer à l'utilisateur ce que l'assistant sait traiter et "
        "pourquoi une question suit tel chemin."
    ),
)
async def routes(
    _utilisateur: dict = Depends(exiger_permission(_PERMISSION_ASSISTANT)),
) -> dict[str, Any]:
    return query_router.referentiel_routes()


@router.get(
    "/referentiel",
    summary="Périmètre et garanties de l'assistant",
    description=(
        "Expose ce que l'assistant sait réellement calculer : étapes du "
        "pipeline, garanties, catalogue des indicateurs (avec leur unité et le "
        "module qui les autorise), intentions reconnues et état du modèle de "
        "langage. Sert à alimenter les suggestions de l'interface et à "
        "documenter pourquoi telle question ne peut pas être répondue."
    ),
)
async def referentiel(
    _utilisateur: dict = Depends(exiger_permission(_PERMISSION_ASSISTANT)),
) -> dict[str, Any]:
    return assistant_service.referentiel_assistant()


@router.get(
    "/exercices",
    summary="Exercices disponibles",
    description=(
        "Exercices présents dans au moins une source (budget, population, "
        "remboursements), du plus récent au plus ancien."
    ),
)
async def exercices(
    _utilisateur: dict = Depends(exiger_permission(_PERMISSION_ASSISTANT)),
) -> dict[str, Any]:
    return {"exercices": await _exercices_disponibles()}


@router.get(
    "/etat",
    summary="État du service de modèle de langage",
    description=(
        "Teste la joignabilité du service configuré. Hors périmètre du "
        "traitement d'une question : l'assistant reste utilisable sans modèle, "
        "chaque réponse étant alors produite par le backend."
    ),
)
async def etat(
    _utilisateur: dict = Depends(exiger_permission(_PERMISSION_ASSISTANT)),
) -> dict[str, Any]:
    try:
        return await llm_service.verifier_disponibilite()
    except Exception as erreur:  # noqa: BLE001
        logger.warning("Diagnostic du modèle indisponible : %s", erreur)
        raise ErreurInterne(
            "Le service de modèle de langage n'a pas pu être interrogé."
        ) from erreur
