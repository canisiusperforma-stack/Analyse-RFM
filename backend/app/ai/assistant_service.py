"""Assistant conversationnel de la plateforme — pipeline imposé.

Le traitement d'une question suit exactement les huit étapes attendues :

     1. Question utilisateur      — reçue par `repondre`
     2. Analyse de la question    — `query_analyzer.analyser_question`
     3. Identification            — `indicator_service.identifier`
        de l'indicateur
     4. Requête backend           — fonction `collecter` de l'indicateur
     5. Calcul exact              — fonction `calculer` de l'indicateur
     6. Résultat structuré        — `indicator_service.ResultatStructure`
     7. LLM                       — `prompt_manager` puis `llm_service.completer`
     8. Explication naturelle      — texte renvoyé, après contrôle des chiffres

        et le contrôle final de `response_validator`, qui rejette toute valeur
        absente du résultat structuré.

Les étapes 2 à 6 n'appellent jamais de modèle. C'est ce qui rend la règle
fondamentale vérifiable : le modèle ne choisit ni la source des données, ni
l'indicateur, ni la formule, ni le mois retenu. Il reçoit à l'étape 7 un
résultat déjà calculé et n'a plus qu'à le rédiger.

Trois garde-fous encadrent la génération :

- **Donnée absente** — si l'étape 5 ne peut pas aboutir, le modèle n'est pas
  appelé. La réponse indique explicitement quelle information manque et
  pourquoi, plutôt que de laisser le modèle combler le vide.
- **Chiffre inventé** — si la réponse de l'étape 8 contient une valeur absente
  du résultat structuré, elle est rejetée et remplacée par la formulation
  déterministe construite par le code.
- **Modèle indisponible** — le repli est le même texte déterministe, ce qui
  rend l'assistant utilisable même sans service de modèle configuré.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from typing import Any, Optional

from app.ai import (
    context_builder,
    indicator_service,
    llm_service,
    prompt_fusion,
    prompt_manager,
    query_analyzer,
    query_router,
)
from app.ai.indicator_service import (
    ABSENT,
    UNITE_DUREE,
    UNITE_EFFECTIF,
    UNITE_MONTANT,
    UNITE_POURCENTAGE,
    UNITE_TEXTE,
    Mesure,
    ResultatStructure,
)
from app.ai.query_analyzer import INTENTION_HORS_PERIMETRE, IntentionQuery
from app.ai.response_validator import assainir, construire_index, valider_reponse
from app.config import settings
from app.rag import grounding, rag_service, retriever
from app.rag.retriever import Source
from app.schemas.assistant import ContexteAssistant, DocumentCite, ReponseAssistant
from app.services.permission_service import utilisateur_a_permission
from app.utils.errors import ErreurForbidden, ErreurValidation
from app.utils.logging import get_logger

logger = get_logger(__name__)

PERMISSION_ASSISTANT = "assistant:utiliser"

#: Permission du canal documentaire. C'est `documents:voir`, celle qu'exige
#: déjà `POST /documents/question` : le canal documentaire de l'assistant doit
#: ouvrir exactement le même périmètre que l'endpoint documentaire existant.
#: En inventer une nouvelle aurait créé, sans le vouloir, deux façons
#: d'accéder aux mêmes contenus — et une seule des deux aurait été gérée.
PERMISSION_DOCUMENTS = "documents:voir"

REGLE_EXPOSEE = (
    "Les chiffres de cette réponse proviennent exclusivement du backend, "
    "calculés avant toute génération. Aucun n'est estimé, extrapolé ni inventé "
    "par un modèle de langage."
)

# --- Rendu des valeurs (étape 8) -------------------------------------------

# La précision d'affichage d'un pourcentage vaut 0,1 point : c'est la
# tolérance du validateur, qui accepte un nombre à une décimale à condition
# qu'il corresponde à une donnée autorisée. Les deux seuils sont donc alignés.
PRECISION_POURCENTAGE = 4


def formater_mesure(mesure: Mesure) -> str:
    """Rend une mesure dans son unité, sans jamais la recalculer.

    Le rendu est une mise en forme, pas un calcul : la valeur et sa précision
    proviennent de `indicator_service`. Le format est celui de
    `prompt_manager.formater_valeur`, afin que le modèle recopie exactement
    l'écriture que l'utilisateur a déjà lue ailleurs dans l'application.
    """
    return prompt_manager.formater_valeur(mesure.valeur, mesure.unite)


def _libelle_avec_valeur(mesure: Mesure) -> str:
    return f"{mesure.libelle} : {formater_mesure(mesure)}"


# ---------------------------------------------------------------------------
# Étape 8 : explication déterministe
# ---------------------------------------------------------------------------


def reponse_deterministe(resultat: ResultatStructure) -> str:
    """Texte rédigé par le code à partir du résultat structuré.

    C'est le filet de sécurité de l'assistant : il est produit sans aucun
    appel au modèle, et sert de réponse finale lorsque le modèle est absent,
    bavard, ou lorsqu'une donnée manque.
    """
    if resultat.statut == ABSENT:
        return _reponse_absence(resultat)

    lignes = [f"{resultat.libelle} :"]

    principale = next(
        (mesure for mesure in resultat.mesures if mesure.unite != UNITE_TEXTE), None
    )
    if principale is not None:
        lignes[0] = f"{resultat.libelle} — {formater_mesure(principale)}"

    detail = next(
        (
            mesure
            for mesure in resultat.mesures
            if mesure.cle == "mois" and mesure.unite == UNITE_TEXTE
        ),
        None,
    )
    if detail is not None and principale is not None:
        lignes.append(f"Il s'agit du {formater_mesure(detail)}.")
    elif detail is not None:
        lignes.append(f"Période concernée : {formater_mesure(detail)}.")

    complementaires = [
        mesure
        for mesure in resultat.mesures
        if mesure.cle not in ("mois", principale.cle if principale else "")
    ]
    if complementaires:
        lignes.append(
            " — ".join(_libelle_avec_valeur(mesure) for mesure in complementaires)
            + "."
        )

    if resultat.texte:
        lignes.append(f"{resultat.texte.capitalize()}.")

    if resultat.note:
        lignes.append(f"Valeur {resultat.note}.")

    return "\n".join(lignes)


def _reponse_absence(resultat: ResultatStructure) -> str:
    """Formulation explicite d'une donnée absente.

    Le motif vient du backend : il nomme la raison technique plutôt que de
    se contenter d'un « je ne sais pas », ce qui permet à l'utilisateur de
    savoir s'il doit importer des données ou changer d'exercice.
    """
    motif = resultat.absence or "Cette information n'est pas disponible en base."
    return (
        f"Cette information n'est pas disponible : {motif}\n\n"
        "L'assistant ne produit aucune estimation à la place d'une donnée "
        "absente. Vérifiez que les données ont été importées pour l'exercice "
        "demandé, ou formulez une autre question."
    )


def _reponse_hors_perimetre() -> str:
    return (
        "Cette question ne porte pas sur les données de la plateforme.\n\n"
        "L'assistant sait calculer, à partir des données du backend : le taux "
        "d'exécution et les montants du budget, la population et ses "
        "répartitions, le croisement entre situation et statut RFM, l'évolution "
        "mensuelle des remboursements et leurs mois extrêmes, les statistiques "
        "descriptives, les anomalies détectées et les prévisions.\n\n"
        "Reformulez la question avec l'un de ces éléments."
    )


# ---------------------------------------------------------------------------
# Contrôle d'accès
# ---------------------------------------------------------------------------


def _verifier_acces(utilisateur: Optional[dict[str, Any]]) -> None:
    if utilisateur is None:
        return
    if not utilisateur_a_permission(utilisateur, PERMISSION_ASSISTANT):
        raise ErreurForbidden(
            "Votre rôle ne permet pas d'utiliser l'assistant conversationnel."
        )


def _controler_permission_indicateur(
    resultat: ResultatStructure,
    utilisateur: Optional[dict[str, Any]],
) -> None:
    """Vérifie que l'utilisateur peut consulter le module de l'indicateur.

    Le module est celui du *fournisseur* de la donnée (`analyses` pour la série
    des remboursements), et non celui de l'indicateur : c'est lui qui a été
    interrogé.
    """
    if utilisateur is None:
        return
    indicateur = indicator_service.INDICATEURS_PAR_CODE.get(resultat.indicateur)
    if indicateur is None:
        return
    if not utilisateur_a_permission(utilisateur, indicateur.permission):
        raise ErreurForbidden(
            f"Votre rôle ne permet pas de consulter le module "
            f"« {indicateur.module} », nécessaire pour répondre à cette question."
        )


def _normaliser_historique(
    historique: Optional[list[dict[str, str]]],
) -> list[dict[str, str]]:
    if not historique:
        return []
    nettoye: list[dict[str, str]] = []
    for tour in list(historique)[-settings.LLM_TOURS_HISTORIQUE * 2 :]:
        if not isinstance(tour, dict):
            continue
        role = tour.get("role")
        contenu = str(tour.get("content") or "").strip()
        if role in ("user", "assistant") and contenu:
            nettoye.append({"role": role, "content": contenu[:2000]})
    return nettoye


# ---------------------------------------------------------------------------
# Étapes 1 à 8
# ---------------------------------------------------------------------------


async def repondre(
    question: str,
    utilisateur: Optional[dict[str, Any]] = None,
    historique: Optional[list[dict[str, str]]] = None,
    exercice: Optional[int] = None,
) -> dict[str, Any]:
    """Traite une question et renvoie une réponse auditable et sourcée."""
    debut = datetime.now(timezone.utc)

    # --- Étape 1 : question utilisateur ---------------------------------
    if not question or not question.strip():
        raise ErreurValidation("La question ne peut pas être vide.")
    if len(question) > settings.LLM_QUESTION_MAX:
        raise ErreurValidation(
            f"La question dépasse {settings.LLM_QUESTION_MAX} caractères."
        )

    _verifier_acces(utilisateur)

    # --- Étape 2 : analyse de la question -------------------------------
    intention = query_analyzer.analyser_question(question)

    if not intention.est_dans_perimetre():
        return _enveloppe(
            question=question,
            reponse=_reponse_hors_perimetre(),
            intention=intention,
            resultat=ResultatStructure(
                indicateur="hors_perimetre",
                libelle="Hors périmètre",
                unite=UNITE_TEXTE,
                statut=ABSENT,
                absence="La question ne porte sur aucun indicateur de la plateforme.",
            ),
            controle={"conforme": True, "note": "hors périmètre, aucun chiffre produit"},
            generee_par="backend",
            modele=None,
            avertissements=[],
            debut=debut,
            hors_perimetre=True,
        )

    exercice_cible = exercice if exercice is not None else intention.exercice

    # --- Étapes 3 à 6 : indicateur, requête, calcul, résultat structuré ---
    resultat, faits = await indicator_service.resoudre(intention, exercice_cible)

    _controler_permission_indicateur(resultat, utilisateur)

    avertissements: list[str] = []
    if exercice_cible is None:
        avertissements.append(
            "Aucun exercice n'a été précisé : le plus récent disponible est utilisé."
        )
    if resultat.statut == ABSENT:
        avertissements.append(
            "Les données nécessaires à cet indicateur sont absentes : la "
            "réponse est produite sans estimation."
        )

    # Étape 6b : un calcul exact a été fait, un texte déterministe aussi.
    # Il sert de repli et de référence de contrôle.
    reponse_fiable = reponse_deterministe(resultat)

    # --- Étape 7 : le LLM ne reçoit que des valeurs déjà calculées ------
    if resultat.statut == ABSENT or not llm_service.llm_actif():
        return _enveloppe(
            question=question,
            reponse=reponse_fiable,
            intention=intention,
            resultat=resultat,
            controle={
                "conforme": True,
                "note": (
                    "donnée absente : réponse déterministe, sans appel au modèle"
                    if resultat.statut == ABSENT
                    else "assistant IA désactivé : réponse déterministe du backend"
                ),
            },
            generee_par="backend",
            modele=None,
            avertissements=avertissements,
            debut=debut,
            faits=faits,
        )

    messages = prompt_manager.construire_messages(
        question=question,
        resultat=resultat,
        sources=resultat.sources,
        historique=_normaliser_historique(historique),
    )

    try:
        generation = await llm_service.completer(messages)
    except llm_service.ErreurLLM as erreur:
        logger.warning("Bascule sur la réponse déterministe : %s", erreur)
        avertissements.append(
            "Le service de modèle de langage est indisponible ; la réponse a "
            "été produite directement par le backend."
        )
        return _enveloppe(
            question=question,
            reponse=reponse_fiable,
            intention=intention,
            resultat=resultat,
            controle={"conforme": True, "note": f"modèle indisponible : {erreur}"},
            generee_par="backend",
            modele=None,
            avertissements=avertissements,
            debut=debut,
            faits=faits,
        )

    # --- Étape 8 : explication naturelle, contrôlée ---------------------
    index = construire_index(
        {"resultat": resultat.resume(), "faits": faits if faits is not None else {}}
    )
    validation = valider_reponse(generation.texte, resultat.resume(), index=index)
    controle = validation.resume()

    if validation.valide:
        return _enveloppe(
            question=question,
            reponse=generation.texte.strip(),
            intention=intention,
            resultat=resultat,
            controle=controle,
            generee_par="llm",
            modele=generation.modele,
            avertissements=avertissements,
            debut=debut,
            faits=faits,
        )

    logger.warning(
        "Réponse du modèle rejetée (%s chiffre(s) non autorisé(s)) ; repli sur "
        "la réponse backend.",
        validation.nombre_ecarts,
    )
    avertissements.append(
        "La réponse produite par le modèle mentionnait des valeurs absentes du "
        "résultat calculé ; elle a été remplacée par une réponse rédigée par "
        "le backend."
    )
    return _enveloppe(
        question=question,
        reponse=reponse_fiable,
        intention=intention,
        resultat=resultat,
        controle={**controle, "fallback": "reponse backend (chiffres non vérifiés)"},
        generee_par="backend",
        modele=generation.modele,
        avertissements=avertissements,
        debut=debut,
        faits=faits,
        rejetee=assainir(generation.texte, validation),
    )


def _enveloppe(
    *,
    question: str,
    reponse: str,
    intention: IntentionQuery,
    resultat: ResultatStructure,
    controle: dict[str, Any],
    generee_par: str,
    modele: Optional[str],
    avertissements: list[str],
    debut: datetime,
    hors_perimetre: bool = False,
    faits: Any = None,
    rejetee: Optional[str] = None,
) -> dict[str, Any]:
    """Enveloppe commune : réponse, provenance du calcul et traçabilité."""
    return {
        "question": question,
        "reponse": reponse,
        "analyse": intention.resume(),
        "resultat": resultat.resume(),
        "exercice": resultat.sources[0].get("exercice") if resultat.sources else None,
        "sources": resultat.sources[: settings.LLM_SOURCES_MAX],
        "controle": controle,
        "generee_par": generee_par,
        "modele": modele,
        "regle": REGLE_EXPOSEE,
        "avertissements": avertissements,
        "hors_perimetre": hors_perimetre,
        "reponse_rejetee": rejetee,
        "duree_ms": int((datetime.now(timezone.utc) - debut).total_seconds() * 1000),
    }


def referentiel_assistant() -> dict[str, Any]:
    """Périmètre et garanties de l'assistant, exposés par l'API."""
    return {
        "regle": REGLE_EXPOSEE,
        "pipeline": [
            "Question utilisateur",
            "Analyse de la question (code)",
            "Identification de l'indicateur (code)",
            "Requête backend",
            "Calcul exact (code)",
            "Résultat structuré",
            "Génération par le modèle de langage",
            "Explication naturelle contrôlée",
        ],
        "garanties": [
            "L'intention, l'indicateur et la formule sont déterminés par le code, pas par le modèle.",
            "Le calcul exact est exécuté par le backend avant toute génération.",
            "Le modèle ne reçoit que des valeurs déjà calculées et déjà formatées.",
            "Chaque chiffre de la réponse est rapproché du résultat structuré.",
            "Une donnée absente est déclarée comme telle, jamais estimée.",
            "En cas de coupure ou de doute, une réponse backend est renvoyée.",
        ],
        "indicateurs": indicator_service.referentiel_indicateurs(),
        "intentions": query_analyzer.referentiel_intentions()["intentions"],
        "modele": {
            "actif": llm_service.llm_actif(),
            "nom": settings.LLM_MODELE if llm_service.llm_actif() else None,
            "temperature": settings.LLM_TEMPERATURE if llm_service.llm_actif() else None,
        },
    }


# ===========================================================================
# Orchestration fusionnée (DATA / RAG / DATA_RAG / INCONNUE)
# ===========================================================================
#
# `repondre`, ci-dessus, reste inchangé : c'est le chemin DATA historique,
# éprouvé par `tests/test_assistant.py`. Il n'est ni redirigé ni réécrit. Un
# chemin neuf se construit à côté, et c'est seulement à l'API que le choix se
# pose.
#
# Ce que le chemin fusionné change, et qui justifie une fonction distincte :
#
# - il **route** avant d'interroger quoi que ce soit, là où `repondre`
#   supposait le chemin DATA ;
# - il **dégrade** au lieu de refuser. Une partie inaccessible n'annule pas
#   l'autre : un utilisateur qui peut lire les documents mais pas le budget
#   obtient quand même la partie documentaire, avec la limite énoncée. Refuser
#   tout aurait été plus simple, et aurait été une régression fonctionnelle ;
# - il **compose** deux provenances distinctes sans les confondre.
#
# Ordre d'exécution, et pourquoi il est fixe
#     Le routeur est consulté avant toute source, pour qu'aucune requête ne
#     parte vers un service inutile. Le budget est sollicité avant la recherche
#     documentaire : c'est le calcul qui décide si la comparaison a un objet,
#     et interroger les documents pour rien coûte une recherche vectorielle
#     pour un résultat qui sera jeté. Le modèle est appelé en dernier, une fois
#     le contexte figé. Aucune étape ne peut donc produire une affirmation que
#     les précédentes ne justifient pas.


#: Réponse produite lorsqu'une période est nécessaire mais n'a pas pu être
#: déduite. Elle est rédigée par le code et n'interroge aucune source : demander
#: « pour quel exercice ? » ne justifie pas de lancer une recherche avant d'avoir
#: la réponse.
MESSAGE_CLARIFICATION = (
    "Pour répondre précisément, j'ai besoin de connaître l'exercice concerné."
)


def reponse_deterministe_fusion(contexte: ContexteAssistant) -> str:
    """Texte de repli du chemin fusionné, rédigé par le code.

    Même exigence que `reponse_deterministe` — aucun appel au modèle — mais
    appliquée à deux provenances. Elle assume sa propre forme : elle juxtapose
    ce que les données montrent et ce que les documents disent, **sans les
    rapprocher**, et le dit explicitement.

    Cette absence de rapprochement est délibérée, et c'est le point le plus
    important de cette fonction. Rapprocher, c'est dire « 78,4 % est inférieur
    au seuil de 80 % » — un énoncé vrai, mais que le code ne peut pas établir
    seul : il ignore que le seuil s'applique, puisque personne ne lui a déclaré
    que ces deux nombres sont de même nature. Le laisser au seul code reviendrait
    à faire une comparaison arbitraire ; le faire au modèle laisserait passer une
    interprétation non contrôlée. En l'annonçant, on ne perd rien : l'utilisateur
    sait qu'il a les deux moitiés, et le modèle les rapproche quand il est
    disponible — sous contrôle des chiffres.
    """
    parties: list[str] = []
    donnees = contexte.data_context

    if donnees is not None and donnees.statut != ABSENT:
        lignes = [f"{donnees.libelle} :"]
        principale = next(
            (mesure for mesure in donnees.mesures if mesure.unite != UNITE_TEXTE),
            None,
        )
        if principale is not None:
            lignes[0] = f"{donnees.libelle} — {principale.valeur_affichee}"
        complement = [
            mesure
            for mesure in donnees.mesures
            if principale is not None and mesure.cle != principale.cle
        ]
        if complement:
            lignes.append(
                " — ".join(
                    f"{mesure.libelle} : {mesure.valeur_affichee}"
                    for mesure in complement
                )
                + "."
            )
        if donnees.calcul:
            lignes.append(f"Valeur {donnees.calcul}.")
        parties.append("\n".join(lignes))
    elif donnees is not None:
        motif = donnees.absence or "Cette information n'est pas disponible en base."
        parties.append(
            f"Cette information n'est pas disponible : {motif}\n\n"
            "Aucune estimation n'est produite à la place d'une donnée absente."
        )

    if contexte.document_context:
        introduction = (
            "Les documents indiquent :"
            if donnees is not None and donnees.statut != ABSENT
            else "Voici les passages des documents autorisés qui répondent le "
            "mieux à votre question. Ils sont restitués tels quels."
        )
        extraits = [introduction]
        for document in contexte.document_context:
            extraits.append(f"[{document.etiquette}] {document.document}\n{document.extrait}")
        parties.append("\n\n".join(extraits))

    if (
        contexte.data_context is not None
        and contexte.data_context.statut != ABSENT
        and contexte.document_context
    ):
        parties.append(
            "Les chiffres et les règles ci-dessus proviennent de deux origines "
            "distinctes. Leur rapprochement n'est pas effectué ici : il est "
            "produit par le modèle de langage lorsqu'il est disponible, sous "
            "contrôle automatique des valeurs citées."
        )

    for limite in contexte.limites:
        parties.append(limite)

    if not parties:
        parties.append(
            "Aucun élément n'a pu être obtenu pour cette question, "
            "sur aucune source autorisée."
        )

    return "\n\n".join(parties)


def _autorise_documents(utilisateur: Optional[dict[str, Any]]) -> bool:
    """Le canal documentaire est-il ouvert à cet utilisateur ?

    Un `utilisateur` absent signifie « contexte interne, non contraint » : c'est
    le comportement des tests et du traitement par lots. Un `utilisateur` présent
    mais sans la permission voit le canal documentaire se fermer, avec la limite
    énoncée dans la réponse — jamais une erreur.
    """
    if utilisateur is None:
        return True
    return utilisateur_a_permission(utilisateur, PERMISSION_DOCUMENTS)


async def _collecter_documents(
    question: str,
    route: query_router.RouteQuery,
    utilisateur: Optional[dict[str, Any]],
    documents: Optional[list[str]],
) -> tuple[list[Source], Optional[str]]:
    """Extraits documentaires retenus, et motif de leur absence éventuelle.

    Renvoie un couple plutôt qu'une liste simple parce que l'absence a deux
    causes **qui ne se ressemblent pas** : une recherche menée sans succès
    (l'utilisateur doit alors savoir qu'il existe des documents) et une
    recherche non menée (permission, RAG désactivé). Les confondre laisserait
    croire que les documents ne traitent pas du sujet alors qu'ils n'ont pas été
    consultés.
    """
    if not route.requiert_documents:
        return [], None

    if not settings.RAG_ENABLED:
        return [], "La recherche documentaire est désactivée sur ce déploiement."

    if not _autorise_documents(utilisateur):
        return [], (
            "Les documents ne sont pas accessibles à votre rôle : aucune règle "
            "documentaire n'est citée."
        )

    resultat = await rag_service.rechercher(
        question=question,
        utilisateur=utilisateur,
        nombre=settings.ASSISTANT_RAG_TOP_K,
        documents=documents or None,
    )

    if resultat.vide or not resultat.suffisant:
        return [], (
            "Aucun extrait de document autorisé ne correspond à cette question : "
            "aucune règle n'est citée."
        )

    return retriever.construire_sources(resultat), None


def _controler_citations(
    reponse: str,
    documents: list[Source],
    index: Any,
) -> tuple[bool, dict[str, Any], Optional[str]]:
    """Contrôle d'ancrage d'une réponse de fusion.

    Deux contrôles indépendants sont appliqués, et ils ne se recouvrent pas :

    - `grounding.valider` vérifie que chaque marqueur `[S1]` écrit désigne un
      extrait **réellement fourni**, et que toute affirmation d'absence est
      cohérente avec la présence effective d'extraits ;
    - `valider_reponse` rapproche chaque chiffre de l'index des valeurs
      autorisées, documents compris.

    Les deux sont nécessaires, et l'ordre n'est pas indifférent : l'index retient
    le contenu des extraits, donc une valeur affirmée sans citation mais présente
    dans un extrait passerait le contrôle numérique ; à l'inverse, un marqueur
    valide ne dit rien des chiffres qu'il accompagne.
    """
    verdict = grounding.valider(reponse, documents)

    numerique = valider_reponse(reponse, None, index=index)

    controle = {
        "chiffres": numerique.resume(),
        "ancrage": verdict.to_dict(),
        "conforme": bool(verdict.conforme and numerique.valide),
    }

    if numerique.valide and verdict.conforme:
        return True, controle, None

    if not verdict.conforme:
        return False, controle, "ancrage documentaire"

    return False, controle, f"{numerique.nombre_ecarts} chiffre(s) non autorisé(s)"


async def orchestrer(
    question: str,
    utilisateur: Optional[dict[str, Any]] = None,
    historique: Optional[list[dict[str, str]]] = None,
    exercice: Optional[int] = None,
    documents: Optional[list[str]] = None,
) -> dict[str, Any]:
    """Orchestre une question selon le chemin qu'elle appelle.

    Chemin d'exécution, identique pour les quatre routes :

        1. contrôle d'accès et de longueur ;
        2. **routage** par `query_router`, avant toute source sollicitée ;
        3. arrêt immédiat sur demande de précision, sans interroger quoi que ce
           soit ;
        4. calcul backend, si le chemin exige des données ;
        5. recherche documentaire, si le chemin exige des documents ;
        6. **figeage** du contexte — l'objet `ContexteAssistant` est alors
           complet, et le modèle n'a plus de sources àelles que l'on puisse
           lui ajouter ;
        7. génération, si elle est possible ;
        8. contrôle, et repli sur un texte produit par le code en cas de doute.

    L'étape 6 est celle qui porte la garantie. Tant qu'elle n'a pas eu lieu,
    aucune génération n'est tentée ; une fois qu'elle a eu lieu, le modèle ne
    peut plus élargir sa fenêtre, et chaque valeur qu'il écrit est confrontée à
    l'index de ce contexte figé.
    """
    debut = datetime.now(timezone.utc)

    # --- Étape 1 : accès et longueur -----------------------------------
    if not question or not question.strip():
        raise ErreurValidation("La question ne peut pas être vide.")
    if len(question) > settings.LLM_QUESTION_MAX:
        raise ErreurValidation(
            f"La question dépasse {settings.LLM_QUESTION_MAX} caractères."
        )

    _verifier_acces(utilisateur)

    # --- Étape 2 : routage ----------------------------------------------
    decision = query_router.classifier(question, exercice_impose=exercice)
    route = decision.route
    chemin: list[str] = ["routeur"]

    logger.info(
        "Routage : %s (confiance %.2f) — %s",
        route.intent, route.confiance, route.raison,
    )

    avertissements: list[str] = []

    # Une question sans aucune source identifiable reçoit la présentation du
    # périmètre. C'est le seul chemin qui n'a rien à chercher, et sa réponse la
    # plus utile est alors celle qui dit ce que la plateforme sait faire —
    # auquel cas l'utilisateur reformule au lieu de repartir sans direction.
    if route.intent == query_router.ROUTE_INCONNUE:
        return _enveloppe_fusion(
            question=question,
            route=route,
            reponse=_reponse_hors_perimetre(),
            contexte=ContexteAssistant(question=question, intent=route.intent),
            documents_cites=[],
            sources=[],
            controle={
                "conforme": True,
                "note": "hors périmètre : aucune source interrogée, aucun chiffre produit",
            },
            generee_par="backend",
            modele=None,
            avertissements=avertissements,
            debut=debut,
            chemin=["routeur", "hors_perimetre"],
            hors_perimetre=True,
        )

    # --- Étape 3 : demande de précision --------------------------------
    # Interrompre ici, avant toute source, est le point de l'exercice : une
    # période manquante est une ambiguïté de la question, pas un vide de
    # données. Interroger MongoDB et l'index vectoriel pour découvrir ensuite
    # qu'il fallait demander « pour quel exercice ? » serait un gaspillage
    # double — un coût machine, puis une réponse inutilisable.
    if route.besoin_clarification and settings.ASSISTANT_CLARIFICATION:
        return _enveloppe_fusion(
            question=question,
            route=route,
            reponse=f"{MESSAGE_CLARIFICATION} {route.question_clarification or ''}".strip(),
            contexte=ContexteAssistant(
                question=question,
                intent=route.intent,
            ),
            documents_cites=[],
            sources=[],
            controle={
                "conforme": True,
                "note": "précision demandée avant toute interrogation des sources",
            },
            generee_par="backend",
            modele=None,
            avertissements=avertissements,
            clarification={
                "motif": route.raison,
                "question": route.question_clarification,
                "parametres_manquants": route.parametres_manquants,
            },
            debut=debut,
            chemin=["routeur", "clarification"],
        )

    # --- Étape 4 : calcul backend --------------------------------------
    resultat: Optional[ResultatStructure] = None
    faits: Any = None
    # Motif d'absence documentaire, connu seulement si le chemin le sollicite.
    # Il est initialisé ici plutôt que déclaré dans la branche documentaire :
    # un chemin DATA ne le renseigne jamais, et le référencer ensuite au
    # moment de figer le contexte interromprait le traitement d'un tiers des
    # questions.
    motif: Optional[str] = None

    if route.requiert_donnees:
        chemin.append("indicateurs")
        intention = query_analyzer.analyser_question(question)
        exercice_cible = exercice if exercice is not None else intention.exercice

        resultat, faits = await indicator_service.resoudre(intention, exercice_cible)
        chemin.append("calcul")

        if exercice_cible is None:
            avertissements.append(
                "Aucun exercice n'a été précisé : le plus récent disponible est utilisé."
            )
        if resultat.statut == ABSENT:
            avertissements.append(
                "Les données nécessaires à cet indicateur sont absentes : la "
                "réponse est produite sans estimation."
            )

    # --- Étape 5 : recherche documentaire -------------------------------
    sources_docs: list[Source] = []
    if route.requiert_documents:
        chemin.append("rag")
        sources_docs, motif = await _collecter_documents(
            question, route, utilisateur, documents
        )
        if motif:
            avertissements.append(motif)

    # --- Étape 6 : figeage du contexte ---------------------------------
    chemin.append("contexte")
    contexte = context_builder.construire_contexte(
        route,
        resultat,
        sources_docs,
        # Le motif d'absence documentaire est une **limite**, pas un simple
        # avertissement technique : c'est ce que l'utilisateur doit savoir pour
        # juger la réponse. Les deux notions sont distinctes — « le modèle était
        # indisponible » est un fait d'exécution, « les documents sont inaccessibles
        # à votre rôle » est une frontière de la réponse — et la première version
        # de ce code les confondait, ce qui affichait deux fois la même phrase
        # quand un indicateur était absent : une fois comme limite déduite du
        # contexte, une fois comme avertissement fusionné.
        limites_collecte=[motif] if motif else None,
    )

    index = context_builder.index_valeurs_autorisees(contexte)

    # --- Étape 7 : génération ------------------------------------------
    reponse_fiable = reponse_deterministe_fusion(contexte)

    if not settings.ASSISTANT_FUSION_ENABLED or not llm_service.llm_actif():
        # La réponse déterministe porte elle aussi des marqueurs `[S1]`, elle
        # doit donc subir le même contrôle d'ancrage que la réponse rédigée.
        # L'omettre laisserait `controle.conforme` à `True` par construction —
        # une garantie affichée sans qu'aucun contrôle ne l'ait produite — et
        # surtout empêcherait l'interface de distinguer un document cité d'un
        # document simplement consulté.
        _conforme, controle, _motif = _controler_citations(
            reponse_fiable, sources_docs, index
        )
        controle["note"] = (
            "modèle indisponible : réponse déterministe du backend"
            if not settings.ASSISTANT_FUSION_ENABLED
            else "assistant IA désactivé : réponse déterministe du backend"
        )
        return _enveloppe_fusion(
            question=question,
            route=route,
            reponse=reponse_fiable,
            contexte=contexte,
            documents_cites=sources_docs,
            sources=(resultat.sources if resultat else [])[: settings.LLM_SOURCES_MAX],
            controle=controle,
            generee_par="backend",
            modele=None,
            avertissements=avertissements,
            debut=debut,
            chemin=chemin,
            resultat=resultat,
        )

    messages = prompt_fusion.construire_messages(
        contexte, historique=_normaliser_historique(historique)
    )

    try:
        generation = await llm_service.completer(messages)
    except llm_service.ErreurLLM as erreur:
        logger.warning("Bascule sur la réponse déterministe (fusion) : %s", erreur)
        avertissements.append(
            "Le service de modèle de langage est indisponible ; la réponse a "
            "été produite directement par le backend."
        )
        return _enveloppe_fusion(
            question=question,
            route=route,
            reponse=reponse_fiable,
            contexte=contexte,
            documents_cites=sources_docs,
            sources=(resultat.sources if resultat else [])[: settings.LLM_SOURCES_MAX],
            controle={"conforme": True, "note": f"modèle indisponible : {erreur}"},
            generee_par="backend",
            modele=None,
            avertissements=avertissements,
            debut=debut,
            chemin=chemin,
            resultat=resultat,
        )

    # --- Étape 8 : contrôle de la réponse générée ------------------------
    texte = generation.texte.strip()

    # Le contrôle d'ancrage porte sur les sources **anonymisées** : c'est
    # exactement ce que le modèle a reçu dans le prompt. Contrôler la citation
    # contre le texte brut, que le modèle n'a pas vu, reviendrait à exiger une
    # correspondance sur une information qu'il n'a pas pu utiliser.
    sources_anonymisees = [
        _source_anonymisee(source, document.extrait, document.etiquette)
        for source, document in zip(sources_docs, contexte.document_context)
    ]

    conforme, controle, motif_rejet = _controler_citations(
        texte, sources_anonymisees, index
    )

    if conforme:
        chemin.append("llm")
        return _enveloppe_fusion(
            question=question,
            route=route,
            reponse=texte,
            contexte=contexte,
            documents_cites=sources_docs,
            sources=(resultat.sources if resultat else [])[: settings.LLM_SOURCES_MAX],
            controle=controle,
            generee_par="llm",
            modele=generation.modele,
            avertissements=avertissements,
            debut=debut,
            chemin=chemin,
            resultat=resultat,
        )

    logger.warning(
        "Réponse de fusion rejetée (%s) : repli sur le texte déterministe.",
        motif_rejet,
    )
    avertissements.append(
        "La réponse produite par le modèle ne respectait pas le contrôle des "
        "valeurs autorisées ; elle a été remplacée par un texte produit par le "
        "backend."
    )
    chemin.append("repli")
    return _enveloppe_fusion(
        question=question,
        route=route,
        reponse=reponse_fiable,
        contexte=contexte,
        documents_cites=sources_docs,
        sources=(resultat.sources if resultat else [])[: settings.LLM_SOURCES_MAX],
        controle={**controle, "fallback": "texte déterministe (contrôle échoué)"},
        generee_par="backend",
        modele=generation.modele,
        avertissements=avertissements,
        debut=debut,
        chemin=chemin,
        resultat=resultat,
        rejetee=texte,
    )


def _source_anonymisee(source: Source, contenu: str, etiquette: str) -> Source:
    """Reprend une source en substituant son contenu par l'extrait anonymisé.

    Le contrôle d'ancrage compare la citation aux faits du passage. Lui fournir
    le texte **avant** anonymisation créerait une incohérence : le modèle n'a
    que l'extrait anonymisé sous les yeux, donc il a nécessairement pu citer
    celui-là — que le contrôle ne retrouverait pas dans la source brute. La
    vérification porte donc sur ce que le modèle a réellement reçu.
    """
    return replace(source, contenu=contenu, etiquette=etiquette)


def _enveloppe_fusion(
    *,
    question: str,
    route: query_router.RouteQuery,
    reponse: str,
    contexte: ContexteAssistant,
    documents_cites: list[Source],
    sources: list[dict[str, Any]],
    controle: dict[str, Any],
    generee_par: str,
    modele: Optional[str],
    avertissements: list[str],
    debut: datetime,
    chemin: list[str],
    resultat: Optional[ResultatStructure] = None,
    clarification: Optional[dict[str, Any]] = None,
    rejetee: Optional[str] = None,
    hors_perimetre: bool = False,
) -> dict[str, Any]:
    """Contrat de sortie du chemin fusionné, conforme à `ReponseAssistant`.

    L'enveloppe ne fait que remplir le schéma : elle n'ajoute aucun champ, et
    n'en retire aucun. Le typage littéral `generee_par` du schéma garantit que
    seuls « llm » ou « backend » peuvent sortir d'ici — un chemin qui aurait
    oublié de remplir ce champ échouerait à la construction plutôt que de
    renvoyer une réponse sans auteur.
    """
    cites = [
        DocumentCite(
            etiquette=document.etiquette,
            document=document.document,
            document_id=document.document_id,
            page=document.page,
            reference=document.reference,
            titre=document.titre,
            confidentialite=document.confidentialite,
            score=document.score,
            cite=document.etiquette in (
                controle.get("ancrage", {}).get("citations") or []
            ),
            extrait=document.extrait,
        )
        for document in contexte.document_context
    ]

    exercice = contexte.data_context.periode if contexte.data_context else None

    enveloppe = ReponseAssistant(
        question=question,
        intent=route.intent,
        reponse=reponse,
        data=contexte.data_context,
        documents=cites,
        sources=sources,
        confidence=route.confiance,
        exercice=exercice,
        analyse=route.model_dump(mode="json"),
        resultat=resultat.resume() if resultat else {},
        controle=controle,
        generee_par=generee_par,
        modele=modele,
        regle=REGLE_EXPOSEE,
        avertissements=avertissements,
        limites=contexte.limites,
        clarification=clarification,
        hors_perimetre=hors_perimetre,
        reponse_rejetee=rejetee,
        duree_ms=int((datetime.now(timezone.utc) - debut).total_seconds() * 1000),
        chemin=chemin,
    )
    return enveloppe.model_dump(mode="json")
