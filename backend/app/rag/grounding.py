"""Contrôle d'ancrage de la réponse du chatbot documentaire.

Troisième rempart, après le prompt. Le prompt dit ce qu'il faut faire ; ce
module **vérifie** que la réponse obtenue le fait. Un modèle peut ignorer ses
consignes, notamment pour satis faire l'utilisateur : il n'est pas rare de voir
un assistant compléter un extrait par un chiffre connu du domaine, ou citer une
page qui n'a pas été fournie. Ces deux défaillances sont détectables
mécaniquement, et sont donc rejetées ici.

Trois contrôles
    `citations`     : chaque marqueur `[Sn]` doit désigner une source
                      effectivement fournie. Un `[S7]` alors qu'il n'y a que
                      trois sources est une référence inventée.
    `chiffres`      : chaque nombre écrit doit figurer dans un extrait fourni.
                      Le contrôle numérique existant (`response_validator`) est
                      réutilisé tel quel, ses exemptions d'énumération comprises.
    `remplissage`   : un texte sans aucun marqueur, alors que des sources ont
                      été fournies, est refusé. C'est le signe qu'une affirmation
                      n'a pas été rattachée à sa source.

Ce que le contrôle ne peut pas faire
    Vérifier qu'un chiffre cité appartient bien à la *bonne* source, ou qu'une
    reformulation reste fidèle. Ces contrôles-là demandent un jugement
    sémantique. Le module ne prétend donc pas garantir la vérité de la réponse :
    il garantit qu'elle **ne contient rien que les documents ne contiennent
    pas**, et qu'elle pointe vers des extraits existants. La fidélité du
    raisonnement reste sous la responsabilité du modèle, d'où l'indexation
    systématique des sources et la possibilité de les consulter.

Repli
    `valider` ne lève pas : il rend un verdict. C'est `rag_service` qui décide
    du repli. Une citation cassée est réparable en remplaçant le marqueur ; un
    chiffre non sourcé ne l'est pas et impose de s'en remettre aux extraits.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Optional

from app.ai.response_validator import (
    EcartNumerique,
    construire_index,
    valider_reponse,
)
from app.config import settings
from app.rag.retriever import Source
from app.utils.logging import get_logger

logger = get_logger(__name__)

#: Marqueur de citation produit par le modèle : `[S1]`, `[S12]`.
#: Les crochets sont **exigés** : une citation est une référence entre crochets,
#: et une mention libre comme « annexe S1 » n'est pas une source. La détection
#: reste cependant souple sur la mise en forme interne (`[S 1]`, `[s1]`).
MOTIF_CITATION = re.compile(r"\[\s*[Ss]\s*(\d{1,3})\s*\]")

#: Mention explicite d'absence, qui autorise une réponse sans citation.
#: Le motif est écrit sans diacritiques et appliqué à un texte normalisé, afin
#: que « pas trouvé » et « pas trouve » soient reconnus de la même façon.
MOTIF_ABSENCE = re.compile(
    r"(ne (?:figure|figurent|apparait|apparaissent|est|sont) pas"
    r"|aucun(?:e)? (?:extrait|document|information|mention|reference)"
    r"|pas (?:d'information|de donnee|de donnees|trouve|trouvee|identifie)"
    r"|ne (?:sont|est) pas (?:disponible|disponibles|trouvable|present"
    r"|presente|identifie|identifiee)"
    r"|insuffisant|insuffisante|impossible de (?:repondre|determiner)"
    r"|je n'ai pas)"
)

#: Longueur minimale pour qu'une réponse ne soit pas jugée vide.
_LONGUEUR_MINIMALE = 15


@dataclass
class Probleme:
    """Un manquement constaté dans la réponse."""

    nature: str
    gravite: str
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "nature": self.nature,
            "gravite": self.gravite,
            "detail": self.detail,
        }


@dataclass
class Verdict:
    """Résultat du contrôle d'une réponse."""

    conforme: bool = True
    citations: list[str] = field(default_factory=list)
    sources_non_citees: list[str] = field(default_factory=list)
    citations_inconnues: list[str] = field(default_factory=list)
    ecarts: list[dict[str, Any]] = field(default_factory=list)
    total_chiffres: int = 0
    mention_absence: bool = False
    reparable: bool = True
    problemes: list[Probleme] = field(default_factory=list)
    explication: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "conforme": self.conforme,
            "citations": self.citations,
            "sources_non_citees": self.sources_non_citees,
            "citations_inconnues": self.citations_inconnues,
            "chiffres_verifies": self.total_chiffres - len(self.ecarts),
            "chiffres_inventes": len(self.ecarts),
            "total_chiffres": self.total_chiffres,
            "mention_absence": self.mention_absence,
            "reparable": self.reparable,
            "problemes": [probleme.to_dict() for probleme in self.problemes],
            "explication": self.explication,
        }


def _normaliser(texte: str) -> str:
    """Minuscules sans diacritiques, pour un motif d'absence insensible aux accents."""
    sans_accents = "".join(
        caractere for caractere in unicodedata.normalize("NFD", texte or "")
        if not unicodedata.combining(caractere)
    )
    return sans_accents.lower()


def _faits(sources: list[Source]) -> dict[str, str]:
    """Concentre les extraits en une structure indexable par le validateur.

    Le validateur numérique attend une charge utile à parcourir. Les contenus
    d'extraits y sont placés sous leur étiquette : la valeur autorisée est alors
    rattachée à la source qui la contient, et non au document entier.
    """
    return {source.etiquette: source.contenu for source in sources}


def controler_citations(
    reponse: str,
    sources: list[Source],
) -> tuple[list[str], list[str], list[str]]:
    """Compare les marqueurs de la réponse aux étiquettes fournies.

    Renvoie les étiquettes citées, dans l'ordre d'apparition, les étiquettes
    jamais citées, et les marqueurs qui ne correspondent à aucune source. Les
    doublons sont écartés de la première liste : deux occurrences de `[S1]` dans
    deux phrases ne sont pas deux sources.
    """
    disponibles = [source.etiquette for source in sources]
    permises = set(disponibles)

    citees: list[str] = []
    inconnues: list[str] = []
    for correspondance in MOTIF_CITATION.finditer(reponse or ""):
        etiquette = f"S{correspondance.group(1)}"
        if etiquette not in permises:
            if etiquette not in inconnues:
                inconnues.append(etiquette)
            continue
        if etiquette not in citees:
            citees.append(etiquette)

    non_citees = [etiquette for etiquette in disponibles if etiquette not in citees]
    return citees, non_citees, inconnues


def controler_chiffres(
    reponse: str,
    sources: list[Source],
) -> tuple[bool, int, list[EcartNumerique]]:
    """Vérifie que chaque nombre écrit provient d'un extrait fourni."""
    faits = _faits(sources)
    resultat = valider_reponse(reponse, faits)
    return resultat.valide, resultat.total_chiffres, resultat.ecarts


def mentionne_absence(reponse: str) -> bool:
    """Vrai si la réponse indique ne pas avoir trouvé l'information.

    Une telle réponse est légitime et n'a pas à être citée : dire « je n'ai pas
    trouvé » en s'attribuant une source serait à la fois faux et trompeur. Le
    texte est normalisé avant recherche, pour que l'accentuation n'y change rien.
    """
    return bool(MOTIF_ABSENCE.search(_normaliser(reponse or "")))


def valider(
    reponse: str,
    sources: list[Source],
) -> Verdict:
    """Contrôle complet d'une réponse face aux sources fournies."""
    verdict = Verdict()
    texte = (reponse or "").strip()

    if len(texte) < _LONGUEUR_MINIMALE:
        verdict.conforme = False
        verdict.reparable = False
        verdict.explication = "Réponse vide ou trop courte pour être vérifiée."
        verdict.problemes.append(Probleme(
            nature="reponse_vide",
            gravite="bloquant",
            detail=f"Longueur {len(texte)} caractère(s), minimum {_LONGUEUR_MINIMALE}.",
        ))
        return verdict

    if not sources:
        # Sans source, toute affirmation serait inventée. Seule une mention
        # d'absence est acceptable.
        if mentionne_absence(texte):
            verdict.mention_absence = True
            verdict.explication = "Absence d'information correctement signalée."
            return verdict
        verdict.conforme = False
        verdict.reparable = False
        verdict.explication = "Réponse affirmative sans aucune source fournie."
        verdict.problemes.append(Probleme(
            nature="affirmation_sans_source",
            gravite="bloquant",
            detail="Aucune source n'a été fournie au modèle.",
        ))
        return verdict

    verdict.mention_absence = mentionne_absence(texte)
    citees, non_citees, inconnues = controler_citations(texte, sources)
    verdict.citations = citees
    verdict.sources_non_citees = non_citees
    verdict.citations_inconnues = inconnues

    if inconnues:
        verdict.conforme = False
        verdict.problemes.append(Probleme(
            nature="citation_inconnue",
            gravite="bloquant",
            detail=(
                f"Marqueur(s) {', '.join(inconnues)} ne correspondant à aucune "
                f"source fournie ({', '.join(source.etiquette for source in sources)})."
            ),
        ))

    conformes, total, ecarts = controler_chiffres(texte, sources)
    verdict.total_chiffres = total
    verdict.ecarts = [ecart.to_dict() for ecart in ecarts]
    if not conformes:
        verdict.conforme = False
        # Un chiffre non sourcé n'est pas réparable : il n'y a pas de source à
        # laquelle rattacher l'affirmation, seulement à la retirer.
        verdict.reparable = verdict.reparable and not ecarts
        verdict.problemes.append(Probleme(
            nature="chiffre_non_sourc",
            gravite="bloquant",
            detail=(
                f"{len(ecarts)} chiffre(s) absent(s) des extraits : "
                + ", ".join(ecart.brut for ecart in ecarts[:5])
            ),
        ))

    if not citees and not verdict.mention_absence:
        verdict.conforme = False
        verdict.reparable = False
        verdict.problemes.append(Probleme(
            nature="affirmation_non_citee",
            gravite="bloquant",
            detail=(
                f"{len(sources)} source(s) fournie(s) mais aucun marqueur de "
                "citation dans la réponse."
            ),
        ))

    if verdict.conforme:
        verdict.explication = (
            f"Réponse étayée par {len(citees)} source(s) sur {len(sources)} "
            f"fournie(s), {total} chiffre(s) vérifié(s)."
        )
    else:
        verdict.explication = (
            f"Réponse rejetée : "
            + ", ".join(probleme.nature for probleme in verdict.problemes)
        )
        logger.warning(
            "Réponse RAG rejetée (%s) : %s",
            ", ".join(probleme.nature for probleme in verdict.problemes),
            verdict.explication,
        )

    return verdict


def nettoyer_citations(reponse: str, sources: list[Source]) -> str:
    """Supprime les marqueurs qui ne désignent aucune source.

    Réparation d'apparence : un `[S9]` orphelin ne prouve pas que l'affirmation
    qui le suit est fausse, seulement que sa référence est fausse. Retirer le
    marqueur laisse une affirmation non sourcée, que le second contrôle
    (citations obligatoires) refusera à son tour — sauf si elle porte un chiffre,
    cas où c'est le contrôle numérique qui tranche. Cette fonction n'est donc
    jamais suffisante seule ; elle accompagne le repli.
    """
    permises = {source.etiquette for source in sources}

    def remplacer(correspondance: re.Match) -> str:
        etiquette = f"S{correspondance.group(1)}"
        if etiquette in permises:
            return correspondance.group(0)
        return ""

    return MOTIF_CITATION.sub(remplacer, reponse or "").strip()


def etiqueter_sources(sources: list[Source], citees: list[str]) -> list[Source]:
    """Marque les sources effectivement citées, pour l'affichage."""
    for source in sources:
        source.cite = source.etiquette in citees
    return sources
