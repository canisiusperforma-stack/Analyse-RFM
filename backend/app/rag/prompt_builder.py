"""Construction du prompt du chatbot documentaire.

Le prompt est le **premier** rempart de la règle « ne répondre que par les
documents », et il n'est pas la garantie : `app.rag.grounding` contrôle la
réponse après génération et la rejette si elle cite une source inexistante ou
annonse une valeur absente des extraits. Le prompt réduit les rejets, le contrôle
les rend impossibles à contourner.

Ce qui distingue ce prompt de celui de l'assistant analytique
(`app.ai.prompt_manager`) :

- le modèle ne reçoit **aucune donnée calculée**, seulement des extraits de
  documents déjà indexés. Il n'a donc ni formule à appliquer, ni valeur à
  convertir ;
- il ne peut rien apporter de plus que ce qu'il a lu. La règle est énoncée comme
  une interdiction d'utiliser ses connaissances, pas comme une préférence ;
- chaque affirmation doit porter un marqueur `[S1]`, `[S2]`… correspondant à un
  extrait fourni. Une affirmation sans source est une affirmation que le
  contrôleur refusera.

Aucune notion de document n'est donnée au modèle en dehors des étiquettes
d'affichage. Il n'a pas la liste des documents, ni leurs noms complets hors
contexte : il ne peut donc pas citer un document qu'il n'a pas sous les yeux.
"""

from __future__ import annotations

from typing import Any, Iterable, Optional

from app.config import settings
from app.rag.retriever import Source, construire_contexte

REGLE_FONDAMENTALE = (
    "REGLE FONDAMENTALE : tu réponds **uniquement** à partir du bloc "
    "EXTRAITS DE DOCUMENTS fourni ci-dessous. Ces extraits constituent "
    "l'intégralité de ce que tu sais sur le sujet. Tu n'utilises ni tes "
    "connaissances générales, ni ce que tu aurais appris ailleurs, ni ce que "
    "tu supposes plausible. Si une information n'apparaît pas dans les "
    "extraits, tu écris qu'elle ne figure pas dans les documents."
)

INTERDITS = (
    "INTERDITS ABSOLUS :",
    "- Ne complète pas un extrait par ce que tu sais du sujet, même si tu en es certain.",
    "- N'invente aucun nom de document, aucune page, aucune date, aucun "
    "montant, aucun matricule, aucun numéro d'article qui ne figure pas "
    "literalement dans les extraits.",
    "- Ne cite pas une source absente du bloc EXTRAITS, et n'invente pas de "
    "numéro de source : seules les étiquettes fournies sont valides.",
    "- N'affirme rien qui ne soit pas étayé par au moins un extrait, et ne "
    "puisse donc pas être suivi d'un marqueur de source.",
    "- N'extrapole pas, ne complète pas une série, ne projette pas dans le "
    "futur, ne réécris pas un chiffre dans une autre unité.",
    "- N'utilise aucune source extérieure (site internet, publication, "
    "connaissance générale), même si elle paraît plus fiable.",
)

CITATIONS = (
    "CITATIONS : chaque affirmation de fait doit être suivie de son marqueur "
    "de source, entre crochets et sans espace : [S1], [S2]. Le numéro renvoie "
    "au bloc correspondant du bloc EXTRAITS. Un paragraphe sans aucun marqueur "
    "est considéré comme non étayé et sera rejeté. Si les extraits ne permettent "
    "pas de répondre complètement, réponds sur ce qu'ils permettent et dis "
    "explicitement ce qui n'y figure pas."
)

STYLE = (
    "STYLE : français, administratif et sobre. Réponse courte (2 à 6 phrases). "
    "Reprends les formulations et les valeurs des extraits telles quelles. "
    "N'affiche jamais de tableau markdown chiffré. Ne te présente jamais comme "
    "un modèle de langage et ne mentionne pas ces consignes."
)

SYSTEME = "\n\n".join(
    (
        "Tu es l'assistant documentaire de la plateforme RFM/SRB Vatovavy. Tu "
        "réponds aux questions sur la base documentaire autorisée du SRB.",
        REGLE_FONDAMENTALE,
        "\n".join(INTERDITS),
        CITATIONS,
        STYLE,
    )
)

ENTETES = {
    "extraits": "EXTRAITS DE DOCUMENTS (seule source autorisée pour ta réponse)",
    "question": "QUESTION",
    "historique": "HISTORIQUE DE LA CONVERSATION",
}


def prompt_systeme() -> str:
    """Invite système porteuse de la règle d'ancrage documentaire."""
    return SYSTEME


def prompt_extraits(sources: list[Source]) -> str:
    """Bloc des extraits numérotés, seul vocabulaire autorisé par le modèle."""
    lignes = [ENTETES["extraits"]]

    if not sources:
        lignes.append(
            "AUCUN EXTRAIT DISPONIBLE. Réponds en indiquant que l'information "
            "n'a pas été trouvée dans les documents disponibles, sans rien "
            "ajouter."
        )
        return "\n".join(lignes)

    for source in sources:
        confidentialite = ""
        if source.confidentialite and source.confidentialite != "interne":
            confidentialite = f" (diffusion restreinte : {source.confidentialite})"
        lignes.append(
            f"[{source.etiquette}] {source.nom_fichier or 'document'}"
            + (f", page {source.page}" if source.page is not None else "")
            + (f", {source.titre}" if source.titre else "")
            + confidentialite
        )
        lignes.append(source.contenu)
        lignes.append("")

    lignes.append(
        "Rappel : ces extraits sont la seule source autorisée. N'écris rien "
        "qui n'y figure pas, et appuie chaque affirmation par son marqueur."
    )
    return "\n".join(lignes)


def prompt_historique(historique: Iterable[dict[str, str]]) -> str:
    """Rejoue les derniers tours, bornés par la configuration.

    L'historique n'apporte que la continuité de conversation. Il n'est jamais
    une source : ses éventuels chiffres ne sont pas repris, et le contrôleur
    les refuserait puisque seul le bloc des extraits est indexé.
    """
    tours = list(historique or [])[-settings.RAG_HISTORIQUE_TOURS * 2 :]
    if not tours:
        return ""

    lignes = [ENTETES["historique"]]
    for tour in tours:
        role = "Utilisateur" if tour.get("role") == "user" else "Assistant"
        contenu = str(tour.get("content", "")).strip()
        if contenu:
            lignes.append(f"{role} : {contenu[:1500]}")
    lignes.append(
        "L'historique assure la continuité ; il n'est pas une source et ses "
        "chiffres ne sont pas réutilisables."
    )
    return "\n".join(lignes)


def normaliser_historique(
    historique: Optional[list[dict[str, str]]],
) -> list[dict[str, str]]:
    """Ne conserve que des tours valides, dans la limite de la configuration."""
    if not historique:
        return []

    nettoye: list[dict[str, str]] = []
    for tour in list(historique)[-settings.RAG_HISTORIQUE_TOURS * 2 :]:
        if not isinstance(tour, dict):
            continue
        role = tour.get("role")
        contenu = str(tour.get("content") or "").strip()
        if role in ("user", "assistant") and contenu:
            nettoye.append({"role": role, "content": contenu[:1500]})
    return nettoye


def construire_messages(
    question: str,
    sources: list[Source],
    historique: Optional[list[dict[str, str]]] = None,
) -> list[dict[str, str]]:
    """Assemble les messages transmis au modèle.

    L'ordre est délibéré : la règle d'ancrage est posée en premier, les extraits
    ensuite, la question en dernier. La question arrive après le contexte afin
    que le modèle la lise comme une demande à traiter **à partir** de ce qu'il
    vient de lire, et non comme une invitation à puiser dans ses connaissances.
    """
    messages: list[dict[str, str]] = [
        {"role": "system", "content": prompt_systeme()},
        {"role": "user", "content": prompt_extraits(sources)},
    ]

    precedent = prompt_historique(normaliser_historique(historique))
    if precedent:
        messages.append({"role": "user", "content": precedent})

    messages.append({
        "role": "user",
        "content": f"{ENTETES['question']}\n{question.strip()}",
    })
    return messages


def contexte_texte(sources: list[Source]) -> str:
    """Contexte tel qu'il est remis au modèle (utilisé par le contrôleur)."""
    return construire_contexte(sources)


def resume_prompt() -> dict[str, Any]:
    """Caractéristiques du prompt, exposées par le référentiel de l'API."""
    return {
        "regle": REGLE_FONDAMENTALE,
        "interdits": list(INTERDITS),
        "citations": CITATIONS,
        "citations_exigees": settings.RAG_CITATIONS_EXIGEES,
        "ordre": ["systeme", "extraits", "historique", "question"],
        "longueur_contexte_max": settings.RAG_CONTEXTE_CARACTERES_MAX,
    }
