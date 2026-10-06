"""Orchestration du pipeline RAG documentaire.

Ce module relie les étapes entre elles et tient la règle centrale du besoin :
**le modèle n'est jamais consulté sans sources, et une réponse non fondée
n'est jamais renvoyée.**

Indexation
    `indexer` enchaîne extraction, nettoyage, découpage, vectorisation et
    écriture. Elle est idempotente : relancer l'indexation d'un document remplace
    ses morceaux au lieu de les doubler. Un échec d'extraction n'interrompt rien :
    le document est marqué en erreur et reste consultable, lisiblement indisponible
    pour la recherche.

Réponse
    `repondre` suit un chemin unique, sans exception attendue :

    1. recherche des extraits autorisés au-dessus du seuil ;
    2. **s'il n'y en a aucun, retour immédiat** d'un message d'absence, sans
       appel au modèle. Le modèle n'a rien à quoi répondre ;
    3. constitution du contexte et du prompt ;
    4. appel du modèle ;
    5. contrôle d'ancrage de la réponse ;
    6. en cas de rejet, repli sur les extraits, jamais sur une regeneration.

Le repli est déterministe : il est produit par le code, à partir des extraits
réellement retenus. C'est ce qui garantit qu'un incident du modèle — indisponible,
muet, ou trop inventif — se traduit par une réponse poorest, jamais par une
réponse fausse.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Optional

from bson import ObjectId

from app.ai.llm_service import ErreurLLM, completer
from app.config import settings
from app.rag import (
    document_loader,
    embeddings,
    grounding,
    prompt_builder,
    retriever,
    text_splitter,
)
from app.rag.erreurs import ErreurDocumentaire
from app.rag.retriever import ResultatRecherche, Source
from app.repositories import document_repository
from app.utils.logging import get_logger

logger = get_logger(__name__)

#: Message rendu quand aucun extrait autorisé n'atteint le seuil.
#: Formulé à l'impératif négatif constant : l'utilisateur doit comprendre que
#: la limite vient des documents disponibles, pas d'un échec technique.
MESSAGE_ABSENCE = (
    "Cette information n'a pas été trouvée dans les documents disponibles."
)

#: Précision ajoutée quand des documents ont bien été consultés sans succès.
#: Un silence laisserait croire à l'absence de document ; préciser le nombre de
#: documents autorisés et le seuil évite cette lecture erronée.
SUFFIXE_ABSENCE = (
    " {nb} document(s) autorisé(s) ont été consultés ; aucun extrait ne "
    "correspond à cette question."
)


@dataclass
class ReponseRAG:
    """Réponse du chatbot documentaire, avec ses sources et son traçabilité."""

    reponse: str
    sources: list[Source] = field(default_factory=list)
    trouve: bool = False
    mode: str = "llm"
    question: str = ""
    recherche: Optional[dict[str, Any]] = None
    controle: Optional[dict[str, Any]] = None
    duree_ms: int = 0
    modele: Optional[str] = None
    tokens_entree: Optional[int] = None
    tokens_sortie: Optional[int] = None

    @property
    def nb_sources(self) -> int:
        return len(self.sources)

    def to_dict(self) -> dict[str, Any]:
        return {
            "reponse": self.reponse,
            "sources": [source.resume() for source in self.sources],
            "nb_sources": self.nb_sources,
            "trouve": self.trouve,
            "mode": self.mode,
            "question": self.question,
            "recherche": self.recherche,
            "controle": self.controle,
            "duree_ms": self.duree_ms,
            "modele": self.modele,
            "tokens_entree": self.tokens_entree,
            "tokens_sortie": self.tokens_sortie,
        }


@dataclass
class ResultatIndexation:
    """Issue de l'indexation d'un document."""

    document_id: ObjectId
    succes: bool
    nb_morceaux: int = 0
    nb_caracteres: int = 0
    duree_ms: int = 0
    message: str = ""
    detail: Optional[dict[str, Any]] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "document_id": str(self.document_id),
            "succes": self.succes,
            "nb_morceaux": self.nb_morceaux,
            "nb_caracteres": self.nb_caracteres,
            "duree_ms": self.duree_ms,
            "message": self.message,
            "detail": self.detail,
        }


# --- Indexation -------------------------------------------------------------


async def indexer(
    document_id: ObjectId,
    force: bool = False,
) -> ResultatIndexation:
    """Indexe un document : extraction, découpe, vectorisation, écriture.

    Ne lève pas pour une erreur de contenu : un PDF illisible ou vide doit rester
    listable et supprimable, seulement pas interrogeable. L'échec est enregistré
    sur le document, avec son motif.
    """
    debut = time.perf_counter()
    document = await document_repository.recuperer_document(document_id)

    if document is None:
        raise ErreurDocumentaire("Document introuvable.", etapa="indexation")

    if document.get("statut_indexation") == "indexe" and not force:
        logger.debug(
            "Document %s déjà indexé (%s morceau(s)), indexation ignorée.",
            document_id,
            document.get("nb_morceaux", 0),
        )
        return ResultatIndexation(
            document_id=document_id,
            succes=True,
            nb_morceaux=int(document.get("nb_morceaux") or 0),
            duree_ms=int((time.perf_counter() - debut) * 1000),
            message="Document déjà indexé.",
        )

    file_id = document.get("file_id")
    if not isinstance(file_id, ObjectId):
        raise ErreurDocumentaire(
            "Fichier d'origine absent : le document ne peut pas être indexé.",
            etapa="indexation",
        )

    nom_fichier = str(document.get("nom_fichier") or "")
    await document_repository.enregistrer_etat_indexation(document_id, "en_cours")

    try:
        contenu = await document_repository.lire_fichier(file_id)
    except Exception as erreur:  # noqa: BLE001 — l'échec doit rester tracé, non remonté
        motif = f"Lecture du fichier impossible : {erreur}"
        await document_repository.enregistrer_etat_indexation(document_id, "echec", erreur=motif)
        logger.error("Lecture du fichier %s impossible : %s", file_id, erreur)
        return ResultatIndexation(
            document_id=document_id,
            succes=False,
            duree_ms=int((time.perf_counter() - debut) * 1000),
            message=motif,
        )

    # Extraction puis découpe : `extraire` lève déjà si le texte obtenu est vide,
    # ce qui couvre le cas d'un PDF scanné sans couche texte.
    extrait = None
    try:
        extrait = document_loader.extraire(contenu, nom_fichier)
        morceaux = text_splitter.decouper(extrait)
    except ErreurDocumentaire as erreur:
        await document_repository.enregistrer_etat_indexation(document_id, "echec", erreur=str(erreur))
        logger.warning("Extraction impossible pour %s : %s", document_id, erreur)
        return ResultatIndexation(
            document_id=document_id,
            succes=False,
            duree_ms=int((time.perf_counter() - debut) * 1000),
            message=str(erreur),
            detail={
                "resume_extraction": extrait.resume() if extrait else None,
            },
        )

    if not morceaux:
        motif = "Le texte extrait est trop court pour être découpé en extraits."
        await document_repository.enregistrer_etat_indexation(document_id, "echec", erreur=motif)
        return ResultatIndexation(
            document_id=document_id,
            succes=False,
            duree_ms=int((time.perf_counter() - debut) * 1000),
            message=motif,
            detail={"resume_extraction": extrait.resume()},
        )

    vecteurs = embeddings.vectoriser_plusieurs([morceau.texte for morceau in morceaux])
    nb_morceaux = await document_repository.remplacer_morceaux(
        document_id, document, morceaux, vecteurs
    )

    await document_repository.enregistrer_etat_indexation(
        document_id,
        "indexe",
        nb_morceaux=nb_morceaux,
        metadonnees={
            "nb_caracteres": extrait.nb_caracteres,
            "taille_octets": len(contenu),
            "format_source": extrait.format,
        },
    )

    duree = int((time.perf_counter() - debut) * 1000)
    stats = text_splitter.statistiques(morceaux)
    logger.info(
        "Document %s indexé : %s morceau(s), %s caractère(s), %s ms.",
        document_id, nb_morceaux, extrait.nb_caracteres, duree,
    )
    return ResultatIndexation(
        document_id=document_id,
        succes=True,
        nb_morceaux=nb_morceaux,
        nb_caracteres=extrait.nb_caracteres,
        duree_ms=duree,
        message=f"{nb_morceaux} extrait(s) indexé(s).",
        detail={
            "resume_extraction": extrait.resume(),
            "decoupage": stats,
        },
    )


# --- Recherche --------------------------------------------------------------


async def rechercher(
    question: str,
    utilisateur: Optional[dict[str, Any]] = None,
    nombre: Optional[int] = None,
    documents: Optional[list[Any]] = None,
) -> ResultatRecherche:
    """Recherche les extraits autorisés correspondant à une question.

    L'interface publique de la recherche : elle ne fait aucun appel au modèle et
    renvoie des extraits, pas une réponse. C'est ce qui permet d'exposer une
    simple recherche documentaire à l'interface, distincte du chat.

    `documents` restreint la recherche à un sous-ensemble de la base. Ce
    périmètre est **combiné** à la clause d'accès, jamais substitué à elle : un
    document listé ici mais non autorisé reste inaccessible.
    """
    return await retriever.rechercher(
        question=question,
        utilisateur=utilisateur,
        nombre=nombre,
        documents=documents,
    )


# --- Réponse ----------------------------------------------------------------


def _reponse_absence(
    resultat: ResultatRecherche,
    nb_documents: int,
) -> str:
    """Compose le message rendu quand rien n'a été trouvé.

    Le nombre de documents consultés n'est indiqué que s'il est connu et non
    nul : annoncer « 0 document » quand l'utilisateur n'a accès à rien
    trahirait l'existence de documents, ce que l'ACL ne permet pas de révéler.
    """
    if nb_documents > 0:
        return MESSAGE_ABSENCE + SUFFIXE_ABSENCE.format(nb=nb_documents)
    return MESSAGE_ABSENCE


def _repli_extraits(sources: list[Source], question: str) -> str:
    """Réponse déterministe constituée à partir des extraits retenus.

    Utilisée quand le modèle est indisponible ou quand sa réponse est rejetée au
    contrôle d'ancrage. Elle est produite par le code et non par le modèle : son
    contenu est, par construction, entièrement présent dans les documents. Elle
    assume son propre style — une restitution, pas une synthèse — et le dit,
    pour que l'utilisateur sache qu'il n'a pas une réponse rédigée mais les
    passages correspondants.
    """
    if not sources:
        return MESSAGE_ABSENCE

    introduction = (
        "Voici les passages des documents autorisés qui répondent le mieux à "
        "votre question. Ils sont restitués tels quels : leur formulation fait "
        "foi, et je n'y ajoute aucune interprétation."
    )
    parties = [introduction]
    for source in sources:
        localisateur = f"{source.nom_fichier or 'document'}"
        if source.page is not None:
            localisateur += f", page {source.page}"
        if source.titre:
            localisateur += f", {source.titre}"
        parties.append(f"[{source.etiquette}] {localisateur}\n{source.contenu}")

    parties.append(
        "Ces passages proviennent des documents consultés ; rien d'autre n'a "
        "été utilisé pour formuler cette réponse."
    )
    return "\n\n".join(parties)


async def repondre(
    question: str,
    utilisateur: Optional[dict[str, Any]] = None,
    historique: Optional[list[dict[str, str]]] = None,
    nombre: Optional[int] = None,
    documents: Optional[list[Any]] = None,
) -> ReponseRAG:
    """Répond à une question à partir des seuls documents autorisés.

    Chemin obligatoire, détaillé dans le docstring du module. Le modèle n'est
    appelé qu'après avoir établi que des extraits pertinents existent, et sa
    réponse n'est renvoyée qu'après contrôle d'ancrage.
    """
    debut = time.perf_counter()
    question = (question or "").strip()

    if not question:
        return ReponseRAG(
            reponse="Indiquez une question à laquelle je puisse répondre.",
            question=question,
            trouve=False,
            mode="sans_question",
        )

    resultat = await retriever.rechercher(
        question=question,
        utilisateur=utilisateur,
        nombre=nombre,
        documents=documents,
    )

    if resultat.vide or not resultat.suffisant:
        # Chemin critique : aucun appel au modèle n'est effectué ici. Le modèle
        # n'aurait que ses connaissances générales à opposer à une absence de
        # sources, ce qui est précisément ce que la règle interdit.
        nb_documents = await _compter_documents(utilisateur)
        logger.info(
            "Question « %s » sans source autorisée : réponse d'absence rendue "
            "sans appel au modèle.", question[:80],
        )
        return ReponseRAG(
            reponse=_reponse_absence(resultat, nb_documents),
            sources=[],
            trouve=False,
            mode="absence",
            question=question,
            recherche=resultat.resume(),
            duree_ms=int((time.perf_counter() - debut) * 1000),
        )

    sources = retriever.construire_sources(resultat)
    messages = prompt_builder.construire_messages(question, sources, historique)

    try:
        reponse_llm = await completer(
            messages,
            temperature=settings.RAG_TEMPERATURE,
            tokens_max=settings.RAG_TOKENS_MAX,
        )
    except ErreurLLM as erreur:
        logger.warning(
            "LLM indisponible pour la question « %s » : repli sur les "
            "extraits (%s).", question[:80], erreur,
        )
        return ReponseRAG(
            reponse=_repli_extraits(sources, question),
            sources=sources,
            trouve=True,
            mode="repli_modele_indisponible",
            question=question,
            recherche=resultat.resume(),
            controle={
                "conforme": False,
                "explication": f"Modèle indisponible : {erreur}",
            },
            duree_ms=int((time.perf_counter() - debut) * 1000),
        )

    texte = reponse_llm.texte
    verdict = grounding.valider(texte, sources)
    grounding.etiqueter_sources(sources, verdict.citations)

    if verdict.conforme:
        return ReponseRAG(
            reponse=texte,
            sources=sources,
            trouve=True,
            mode="llm",
            question=question,
            recherche=resultat.resume(),
            controle=verdict.to_dict(),
            duree_ms=int((time.perf_counter() - debut) * 1000),
            modele=reponse_llm.modele,
            tokens_entree=reponse_llm.tokens_entree,
            tokens_sortie=reponse_llm.tokens_sortie,
        )

    # Réponse rejetée : elle n'est pas renvoyée, seulement ses extraits. Le
    # contrôle a échoué précisément parce qu'elle contenait des éléments que les
    # documents ne contiennent pas ; les refaire apparaître, même partiels,
    # contredirait le contrôle.
    return ReponseRAG(
        reponse=_repli_extraits(sources, question),
        sources=sources,
        trouve=True,
        mode="repli_controle_echoue",
        question=question,
        recherche=resultat.resume(),
        controle=verdict.to_dict(),
        duree_ms=int((time.perf_counter() - debut) * 1000),
        modele=reponse_llm.modele,
        tokens_entree=reponse_llm.tokens_entree,
        tokens_sortie=reponse_llm.tokens_sortie,
    )


async def _compter_documents(utilisateur: Optional[dict[str, Any]]) -> int:
    """Nombre de documents indexés visibles par l'utilisateur.

    Volontairement restreint aux documents **indexés** : annoncer « 4 documents
    disponibles » alors que trois sont inextractibles induirait l'utilisateur à
    chercher une information qui n'a jamais pu être indexée.
    """
    from app.models.document import filtre_acces_documents

    try:
        filtre = filtre_acces_documents(utilisateur)
        return await document_repository.compter_documents({
            **filtre,
            "statut_indexation": "indexe",
        })
    except Exception as erreur:  # noqa: BLE001 — un compte ne doit pas faire échouer la réponse
        logger.warning("Comptage des documents visibles impossible : %s", erreur)
        return 0
