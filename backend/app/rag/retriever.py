"""Étapes « Recherche » et « Contexte » du pipeline RAG.

La recherche est **hybride** : similarité vectorielle (`app.rag.vector_store`)
combinée à un score lexical calculé ici. Ce n'est pas un raffinement
décoratif, c'est ce qui rend le seuil de pertinence exploitable. Un vecteur de
n-grammes mesure une proximité de forme ; un extrait qui partage beaucoup de
mots avec la question sans la traiter peut obtenir un score vectoriel honorable,
tandis qu'une référence exacte de la question (localité, numéro d'article,
matricule) mérite d'être pesée davantage. Inversement, le score lexical seul
remonterait des morceaux qui reprennent les mots de la question sans y répondre.

Diversité
    Deux morceaux consécutifs d'un même document se recouvrent, et les mettre
    tous deux dans le contexte n'apporte rien. Un extrait d'un autre document est
    donc préféré à la suite du même texte : la réponse gagne en couverture, et
    les citations portent sur des documents distincts.

Contexte
    Le contexte est un texte numéroté (`[S1]`, `[S2]`, …) où chaque extrait est
    précédé de sa provenance. C'est ce texte, et lui seul, que le modèle reçoit ;
    aucune autre information documentaire ne lui est transmise.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Optional

from app.config import settings
from app.rag import embeddings, vector_store
from app.rag.vector_store import Candidat
from app.utils.logging import get_logger

logger = get_logger(__name__)

#: Jetons trop courts pour être discriminants dans une recherche lexicale.
_LONGUEUR_TERME_MINIMALE = 3

#: Termes d'une phrase : suites alphanumériques, apostrophe interne admise.
TERME = re.compile(r"[\w']+", re.UNICODE)


@dataclass
class ResultatRecherche:
    """Morceaux retenus pour la question, avec leur score et leur seuil."""

    question: str
    morceaux: list[Candidat] = field(default_factory=list)
    score_max: float = 0.0
    seuil: float = 0.0
    compte_rendu: dict[str, Any] = field(default_factory=dict)
    suffisant: bool = False

    @property
    def vide(self) -> bool:
        return not self.morceaux

    def resume(self) -> dict[str, Any]:
        return {
            "question": self.question,
            "nb_sources": len(self.morceaux),
            "score_max": self.score_max,
            "seuil": self.seuil,
            "suffisant": self.suffisant,
            "recherche": self.compte_rendu,
        }


def _normaliser(texte: str) -> str:
    """Minuscules sans diacritiques, pour une comparaison insensible aux accents.

    La décomposition NFD est indispensable : en NFC, « é » est un caractère
    unique (U+00E9) et le retrait des diacritiques combinants ne retirerait
    rien — « Exécution » ne rencontrerait alors jamais « execution ».
    """
    return "".join(
        caractere
        for caractere in unicodedata.normalize("NFD", (texte or "").lower())
        if not unicodedata.combining(caractere)
    )


def _termes(texte: str) -> list[str]:
    return [
        terme
        for terme in TERME.findall(_normaliser(texte))
        if len(terme) >= _LONGUEUR_TERME_MINIMALE
    ]


def score_lexical(question: str, contenu: str) -> float:
    """Proportion des termes distincts de la question présents dans l'extrait.

    Chaque terme recherché ne compte qu'une fois : c'est la **couverture** qui
    est mesurée, non la densité. Un extrait qui répète un mot cent fois ne doit
    pas éclipser un extrait qui emploie une fois chacun tous les mots de la
    question.
    """
    termes = set(_termes(question))
    if not termes:
        return 0.0

    presents = set(_termes(contenu))
    if not presents:
        return 0.0

    return sum(1 for terme in termes if terme in presents) / len(termes)


def _diversifier(
    scores: list[tuple[Candidat, float]],
    maximum: int,
) -> list[Candidat]:
    """Retient les meilleurs morceaux en privilégiant la variété des documents.

    À chaque tour est choisi le meilleur morceau restant dont le document n'est
    pas déjà dans la sélection ; à défaut — et seulement à défaut — le meilleur
    morceau restant, afin de ne jamais renvoyer moins de `maximum` éléments par
    le seul effet d'une règle de diversité.
    """
    if maximum <= 0:
        return []

    retenus: list[Candidat] = []
    documents_vus: set[str] = set()
    restants = list(scores)

    while restants and len(retenus) < maximum:
        inedits = [
            element for element in restants
            if element[0].document_id not in documents_vus
        ]
        pool = inedits or restants
        choisi, _score = max(pool, key=lambda element: element[1])

        restants = [element for element in restants if element[0] is not choisi]
        documents_vus.add(choisi.document_id)
        retenus.append(choisi)

    return retenus


async def rechercher(
    question: str,
    utilisateur: Optional[dict[str, Any]] = None,
    nombre: Optional[int] = None,
    documents: Optional[list[Any]] = None,
    seuil: Optional[float] = None,
) -> ResultatRecherche:
    """Recherche les extraits de documents autorisés répondant à la question.

    Renvoie un résultat vide plutôt qu'une liste de faible pertinence : c'est
    l'appelant (`rag_service`) qui décide de ne pas appeler le modèle. Le seuil
    est évalué ici, la décision appartient au pipeline.
    """
    seuil = settings.RAG_SEUIL_PERTINENCE if seuil is None else seuil
    nombre = nombre or settings.RAG_RECHERCHE_TOP_K
    question = (question or "").strip()

    if not question:
        return ResultatRecherche(question=question, seuil=seuil, suffisant=False)

    vecteur = embeddings.vecteuriser(question)
    candidats, compte_rendu = await vector_store.chercher(
        vecteur_requete=vecteur,
        utilisateur=utilisateur,
        texte_requete=question,
        documents=documents,
    )

    if not candidats:
        return ResultatRecherche(
            question=question,
            seuil=seuil,
            compte_rendu=compte_rendu,
            suffisant=False,
        )

    ponderation = settings.RAG_PONDERATION_DENSE
    scores: list[tuple[Candidat, float]] = []
    for candidat in candidats:
        lexical = score_lexical(
            question, f"{candidat.titre or ''} {candidat.contenu}"
        )
        # Le score dense est un cosinus déjà borné ; le lexical est une
        # proportion. Les deux sont ramenés à [0, 1] avant le fondu, faute de
        # quoi l'échelle de l'un dominerait celle de l'autre.
        dense = max(0.0, min(1.0, float(candidat.score_dense)))
        candidat.score_dense = round(dense, 6)
        scores.append((candidat, ponderation * dense + (1.0 - ponderation) * lexical))

    scores.sort(key=lambda element: element[1], reverse=True)
    meilleur = scores[0][1]

    compte_rendu["seuil"] = seuil
    compte_rendu["ponderation_dense"] = ponderation
    compte_rendu["meilleur_score"] = round(meilleur, 6)

    if meilleur < seuil:
        logger.info(
            "Question « %s » : meilleur score %.4f < seuil %.4f, aucune source "
            "retenue (%s morceau(x) examiné(s)).",
            question[:80],
            meilleur,
            seuil,
            compte_rendu.get("candidats_examines", 0),
        )
        return ResultatRecherche(
            question=question,
            score_max=round(meilleur, 6),
            seuil=seuil,
            compte_rendu=compte_rendu,
            suffisant=False,
        )

    admissibles = [element for element in scores if element[1] >= seuil]
    retenus = _diversifier(admissibles, max(nombre, settings.RAG_SOURCES_MIN))

    return ResultatRecherche(
        question=question,
        morceaux=retenus,
        score_max=round(meilleur, 6),
        seuil=seuil,
        compte_rendu=compte_rendu,
        suffisant=len(retenus) >= settings.RAG_SOURCES_MIN,
    )


# --- Contexte --------------------------------------------------------------


@dataclass
class Source:
    """Une source citable : un extrait, sa provenance et son rang de citation."""

    etiquette: str
    document_id: str
    ordinal: int
    nom_fichier: Optional[str]
    page: Optional[int]
    titre: Optional[str]
    confidentialite: str
    score: float
    contenu: str
    score_relative: float = 0.0
    cite: bool = False

    def reference(self) -> str:
        """Localisateur lisible repris tel quel dans la réponse."""
        elements = []
        if self.page is not None:
            elements.append(f"p. {self.page}")
        if self.titre:
            elements.append(self.titre)
        return " — ".join(elements) if elements else f"morceau {self.ordinal}"

    def resume(self) -> dict[str, Any]:
        return {
            "etiquette": self.etiquette,
            "document_id": self.document_id,
            "morceau": self.ordinal,
            "nom_fichier": self.nom_fichier,
            "reference": self.reference(),
            "page": self.page,
            "titre": self.titre,
            "confidentialite": self.confidentialite,
            "score": self.score,
            "score_relative": self.score_relative,
            "extrait": self.contenu,
            "cite": self.cite,
        }


def construire_sources(resultat: ResultatRecherche) -> list[Source]:
    """Numérote les extraits retenus : `[S1]`, `[S2]`, etc.

    L'ordre suit le score décroissant, et l'étiquette est **stable** : c'est
    celle qui figure dans la citation. Le contrôle qui suit peut ainsi vérifier
    que chaque marqueur écrit par le modèle désigne un extrait réellement
    fourni, et non un rang inventé.
    """
    sources = [
        Source(
            etiquette=f"S{position}",
            document_id=candidat.document_id,
            ordinal=candidat.ordinal,
            nom_fichier=candidat.nom_fichier,
            page=candidat.page,
            titre=candidat.titre,
            confidentialite=candidat.confidentialite,
            score=round(float(candidat.score_dense), 6),
            contenu=candidat.contenu,
        )
        for position, candidat in enumerate(resultat.morceaux, start=1)
    ]

    # Le score est relativisé : un score brut de similarité n'a pas de portée
    # lisible pour un agent, et deux valeurs égales ne signifient pas la même
    # chose selon la question. La relativisation indique la proximité de chaque
    # source avec la meilleure réponse trouvée.
    meilleur = max((source.score for source in sources), default=0.0) or 1.0
    for source in sources:
        source.score_relative = round(
            max(0.0, min(1.0, source.score / meilleur)), 4
        )
    return sources


def construire_contexte(sources: list[Source]) -> str:
    """Assemble le texte des sources, borné par `RAG_CONTEXTE_CARACTERES_MAX`.

    Le bornage cesse d'ajouter un extrait, il ne le coupe pas : un extrait tronqué
    se lirait comme une phrase inachevée et pourrait être cité ainsi. Un extrait est
    donc pris **en entier** ou écarté.

    Deux bornes gouvernent ce choix. La place disponible dans le contexte, d'abord.
    Puis, si plusieurs extraits se disputent cette place, la part équitable de
    chacun : un extrait plus long que `budget / nombre d'extraits` est écarté,
    parce que l'admettre organiserait la réponse sur une vue parcellaire d'un seul
    document alors que d'autres extraits pertinents sont disponibles. Ce plafond
    ne mord pas en usage courant — avec des extraits de 900 caractères pour un
    budget de 12 000, il vaut 2 000 — mais il garantit qu'un document anormalement
    long ne peut pas accaparer le contexte.

    Ce qui est écarté est signalé en fin de contexte, pour que le modèle sache
    qu'il n'a pas tout vu.
    """
    budget = settings.RAG_CONTEXTE_CARACTERES_MAX
    part = max(1, budget // max(len(sources), 1))

    blocs: list[str] = []
    volume = 0
    ecartes = 0

    for source in sources:
        entete = f"[{source.etiquette}] {source.nom_fichier or 'document'}"
        if source.page is not None:
            entete += f", page {source.page}"
        if source.titre:
            entete += f", {source.titre}"
        bloc = f"{entete}\n{source.contenu}"

        if len(bloc) > part or volume + len(bloc) > budget:
            ecartes += 1
            continue

        volume += len(bloc)
        blocs.append(bloc)

    if ecartes:
        blocs.append(
            f"({ecartes} autre(s) extrait(s) écarté(s) pour ne pas dépasser la "
            "longueur de contexte autorisée.)"
        )

    return "\n\n".join(blocs)
