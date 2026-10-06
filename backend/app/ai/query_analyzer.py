"""Analyse déterministe des questions posées à l'assistant.

Ce module est volontairement **sans modèle de langage**. C'est le code — et
lui seul — qui décide quel jeu de données du backend est autorisé à alimenter
la réponse. Le LLM n'intervient qu'ensuite, pour reformuler des chiffres déjà
chargés et déjà validés.

Conséquence directe de cette séparation : le modèle ne peut ni élargir le
périmètre de la question, ni demander une donnée absente du contexte. Toute
valeur annoncée par l'assistant est donc, par construction, une valeur du
backend.

L'analyse repose sur une table de motifs pondérés et sur des expressions
régulières d'entités. Elle ne lève jamais d'exception : une question
incompréhensible est simplement classée « hors périmètre », ce qui donne
lieu à une réponse de périmètre, sans chiffre.

Entités reconnues :
    exercice            — année explicite (2024) ou relative (« dernier exercice »)
    communes             — « commune de X », « région de X », « district de X »
    situations           — actifs, pensionnés
    types_prestation     — « prestation X », « type de prestation X »
    mois                 — « en mars », « mois de mars »
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Optional

from app.utils.logging import get_logger

logger = get_logger(__name__)

INTENTION_SYNTHESE = "synthese_globale"
INTENTION_POPULATION = "population"
INTENTION_BUDGET = "budget"
INTENTION_REMBOURSEMENTS = "remboursements"
INTENTION_ANALYSE_TEMPORELLE = "analyse_temporelle"
INTENTION_STATISTIQUES = "statistiques"
INTENTION_ANOMALIES = "anomalies"
INTENTION_PREVISIONS = "previsions"
INTENTION_SIMULATIONS = "simulations"
INTENTION_HORS_PERIMETRE = "hors_perimetre"

# Type d'agrégation demandé. Il détermine le calcul appliqué par le backend :
# un superlatif (« le mois le plus élevé ») ou une comparaison sont résolus
# en Python, jamais par le modèle.
AGREGATION_TOTAL = "total"
AGREGATION_ARGMAX = "argmax"
AGREGATION_ARGMIN = "argmin"
AGREGATION_COMPARAISON = "comparaison"

MOTIFS_ARGMAX = re.compile(
    r"\b(?:le plus (?:eleve|grand|gros|haut|fort|important)|"
    r"maximum|maximale|maxi|record|au plus haut|point culminant)\b"
)
MOTIFS_ARGMIN = re.compile(
    r"\b(?:le plus (?:bas|petit|faible)|minimum|minimale|mini|"
    r"au plus bas|point bas)\b"
)
MOTIFS_COMPARAISON = re.compile(
    r"\b(?:compare\w*|comparaison\w*|confronte\w*|versus|vs|"
    r"par rapport a|ecart entre|difference entre|face a)\b"
)


INTENTIONS: tuple[str, ...] = (
    INTENTION_SYNTHESE,
    INTENTION_POPULATION,
    INTENTION_BUDGET,
    INTENTION_REMBOURSEMENTS,
    INTENTION_ANALYSE_TEMPORELLE,
    INTENTION_STATISTIQUES,
    INTENTION_ANOMALIES,
    INTENTION_PREVISIONS,
    INTENTION_SIMULATIONS,
    INTENTION_HORS_PERIMETRE,
)

LIBELLES_INTENTIONS: dict[str, str] = {
    INTENTION_SYNTHESE: "Synthèse générale de l'exercice",
    INTENTION_POPULATION: "Population des bénéficiaires",
    INTENTION_BUDGET: "Exécution budgétaire",
    INTENTION_REMBOURSEMENTS: "Remboursements",
    INTENTION_ANALYSE_TEMPORELLE: "Évolution mensuelle",
    INTENTION_STATISTIQUES: "Statistiques descriptives",
    INTENTION_ANOMALIES: "Anomalies détectées",
    INTENTION_PREVISIONS: "Prévisions de consommation",
    INTENTION_SIMULATIONS: "Simulation de scénario",
    INTENTION_HORS_PERIMETRE: "Hors périmètre des données",
}

MOTIF_ANNEE = re.compile(r"\b(19|20)\d{2}\b")
MOTIF_RELATION_EXERCICE = (
    (re.compile(r"dernier exercice|exercice dernier|dernier annee|annee derniere"), -1),
    (re.compile(r"exercice precedent|annee precedente|exercice anterieur"), -2),
    (re.compile(r"cette annee|annee en cours|exercice en cours|exercice courant"), 0),
)
MOTIF_COMMUNE = re.compile(
    r"\b(?:communes?|regions?|districts?|circonscriptions?)\s+(?:de\s+|d['’]\s*)?"
    r"([a-zà-ÿ][a-zà-ÿ' -]{1,40})",
    re.IGNORECASE,
)
MOTIF_TYPE_PRESTATION = re.compile(
    r"\b(?:prestations?|types?\s+de\s+prestations?)\s+(?:de\s+|d['’]\s*)?"
    r"([a-zà-ÿ][a-zà-ÿ' -]{1,40})",
    re.IGNORECASE,
)

MOIS_NOMMES: dict[str, int] = {
    "janvier": 1, "janv": 1,
    "fevrier": 2, "fevr": 2,
    "mars": 3,
    "avril": 4, "avr": 4,
    "mai": 5,
    "juin": 6,
    "juillet": 7, "juil": 7,
    "aout": 8,
    "septembre": 9, "sept": 9,
    "octobre": 10, "oct": 10,
    "novembre": 11, "nov": 11,
    "decembre": 12, "dec": 12,
}

MOTIF_MOIS = re.compile(
    r"\b(?:en|du|mois\s+de|au\s+cours\s+du)\s+("
    + "|".join(sorted(MOIS_NOMMES, key=len, reverse=True))
    + r")\b",
    re.IGNORECASE,
)

STOPWORDS_FR: frozenset[str] = frozenset(
    {
        "de", "du", "des", "le", "la", "les", "un", "une", "et", "ou", "en",
        "pour", "par", "sur", "dans", "avec", "sans", "au", "aux", "ce", "cette",
        "ces", "que", "qui", "quoi", "comment", "quel", "quelle", "quels",
        "quelles", "est", "sont", "ont", "a", "ont ils", "nous", "je", "mon",
        "ma", "mes", "nos", "notre", "peux", "peut", "tu", "vous", "il", "elle",
        "y a", "y", "plus", "moins", "tres", "beaucoup", "un peu", "donne",
        "donne moi", "donnez", "dis", "dis moi", "explique", "explique moi",
        "analyse", "synthese", "synthetise", "resume", "resume moi",
    }
)

TABLE_MOTS_CLES: tuple[tuple[str, str, int], ...] = (
    (INTENTION_SYNTHESE, r"synthese|tableau de bord|vue d ensemble|en bref|point general|globalement|situation d ensemble|etat des lieux", 3),
    (INTENTION_POPULATION, r"beneficiaires?|population|recenses?|recensement|actifs?|pensionnes?|demographi\w*|par genre|par sexe|effectif|tranche d age|moyenne d age", 2),
    (INTENTION_BUDGET, r"budget\w*|credits?|lfi|lfr|execution|engage\w*|ordonnance\w*|liquidation|vot[ée]|depenses?|lignes? budgetaires?|disponible|decouvert", 2),
    (INTENTION_REMBOURSEMENTS, r"rembours\w*|demandes? de remboursement|dossiers?|paiements?|payes?|montants? demandes?|montants? payes?|delais? de traitement|statuts? des dossiers|circuits?", 2),
    (INTENTION_ANALYSE_TEMPORELLE, r"evolution|evolutions?|tendances?|mensuel\w*|par mois|au fil des mois|courbe|progression|mois par mois", 2),
    (INTENTION_STATISTIQUES, r"statistiques?|descriptives?|moyennes?|medianes?|quartiles?|ecart type|distributions?|percentiles?|correlations?|histogramme|variance|actifs et pensionnes", 2),
    (INTENTION_ANOMALIES, r"anomalies?|irrregularit\w*|anormal\w*|detect\w*|suspect\w*|fraude|controles?|alertes?", 3),
    (INTENTION_PREVISIONS, r"previsions?|prevoir|prevo\w*|projections?|projeter|consommation future|mois a venir", 3),
    (INTENTION_SIMULATIONS, r"simulations?|simuler|scenarios?|que se passerait|si on|impact budgetaire|sensibilit\w*", 3),
)

MOTIFS_COMPILE: tuple[tuple[str, re.Pattern[str], int], ...] = tuple(
    (
        intention,
        re.compile(r"\b(?:" + motif + r")\b", re.IGNORECASE),
        poids,
    )
    for intention, motif, poids in TABLE_MOTS_CLES
)

SEUIL_CONFIANCE = 0.34
LONGUEUR_MINIMALE = 2


@dataclass
class IntentionQuery:
    """Résultat de l'analyse d'une question : intention et entités."""

    question: str
    intention: str = INTENTION_HORS_PERIMETRE
    agregation: str = AGREGATION_TOTAL
    confiance: float = 0.0
    scores: dict[str, int] = field(default_factory=dict)
    exercice: Optional[int] = None
    exercice_implicite: Optional[int] = None
    communes: list[str] = field(default_factory=list)
    situations: list[str] = field(default_factory=list)
    types_prestation: list[str] = field(default_factory=list)
    mois: Optional[int] = None
    mots_cles: list[str] = field(default_factory=list)
    aucun_mot_cle: bool = False
    # Champ précis à calculer, renseigné par `app.ai.indicator_service` une
    # fois l'indicateur identifié. L'analyse reste pure : elle ne le devine pas.
    indicateur_cle: Optional[str] = None

    @property
    def libelle(self) -> str:
        return LIBELLES_INTENTIONS.get(self.intention, self.intention)

    def est_dans_perimetre(self) -> bool:
        return self.intention != INTENTION_HORS_PERIMETRE

    def resume(self) -> dict[str, Any]:
        return {
            "intention": self.intention,
            "libelle": self.libelle,
            "confiance": round(self.confiance, 3),
            "agregation": self.agregation,
            "exercice": self.exercice,
            "communes": self.communes,
            "situations": self.situations,
            "types_prestation": self.types_prestation,
            "mois": self.mois,
            "hors_perimetre": not self.est_dans_perimetre(),
        }


def _detecter_agregation(question_norm: str) -> str:
    """Recherche le superlatif ou la comparaison demandés par la question.

    Un superlatif impose un calcul de maximum ou de minimum sur une série, et
    une comparaison impose un écart : ces opérations sont faites par le
    backend (`app.ai.indicator_service`), le modèle ne fait que nommer le
    résultat. La comparaison prime sur le superlatif, car « compare le mois le
    plus élevé au plus bas » doit produire les deux extrémités.
    """
    if MOTIFS_COMPARAISON.search(question_norm):
        return AGREGATION_COMPARAISON
    if MOTIFS_ARGMAX.search(question_norm):
        return AGREGATION_ARGMAX
    if MOTIFS_ARGMIN.search(question_norm):
        return AGREGATION_ARGMIN
    return AGREGATION_TOTAL


def _normaliser(texte: str) -> str:
    """Minuscules, sans accents, ponctuation réduite à des espaces."""
    sans_accents = unicodedata.normalize("NFKD", texte.lower())
    sans_accents = "".join(
        caractere
        for caractere in sans_accents
        if not unicodedata.combining(caractere)
    )
    return re.sub(r"[^a-z0-9]+", " ", sans_accents).strip()


def _trier_entites(valeurs: list[str], maximales: int = 3) -> list[str]:
    resultat: list[str] = []
    for valeur in valeurs:
        propre = re.sub(r"\s+", " ", valeur).strip(" -,'’")
        if propre and propre not in resultat:
            resultat.append(propre)
        if len(resultat) >= maximales:
            break
    return resultat


def _extraire_exercice(texte: str, question_norm: str) -> tuple[Optional[int], Optional[int]]:
    """Retourne (exercice_absent, exercice_relatif) déduit de la question."""
    annees = {int(motif.group(0)) for motif in MOTIF_ANNEE.finditer(texte)}
    if not annees:
        annees = {int(motif.group(0)) for motif in MOTIF_ANNEE.finditer(question_norm)}
    explicite = max(annees) if annees else None
    for motif, decalage in MOTIF_RELATION_EXERCICE:
        if motif.search(question_norm):
            return explicite, decalage
    return explicite, None


def _extraire_situations(question_norm: str) -> list[str]:
    situations: list[str] = []
    if re.search(r"\bpensionnes?\b", question_norm):
        situations.append("pensionne")
    if re.search(r"\bactifs?\b", question_norm):
        situations.append("actif")
    return situations


def _calculer_scores(question_norm: str) -> dict[str, int]:
    scores: dict[str, int] = {}
    for intention, motif, poids in MOTIFS_COMPILE:
        trouves = motif.findall(question_norm)
        if trouves:
            scores[intention] = scores.get(intention, 0) + poids * len(trouves)
    return scores


def _mots_significatifs(question_norm: str) -> list[str]:
    return [
        mot
        for mot in question_norm.split()
        if len(mot) >= LONGUEUR_MINIMALE and mot not in STOPWORDS_FR
    ]


def analyser_question(question: str) -> IntentionQuery:
    """Classe une question et en extrait les entités, sans appel au LLM."""
    texte = (question or "").strip()
    question_norm = _normaliser(texte)

    if not question_norm:
        return IntentionQuery(question=texte, aucun_mot_cle=True)

    scores = _calculer_scores(question_norm)
    total = sum(scores.values())

    intention = INTENTION_HORS_PERIMETRE
    confiance = 0.0
    if total:
        intention = max(scores, key=lambda cle: scores[cle])
        confiance = scores[intention] / total

    aucun_mot_cle = not _mots_significatifs(question_norm)
    if aucun_mot_cle or confiance < SEUIL_CONFIANCE:
        intention = INTENTION_HORS_PERIMETRE
        confiance = 0.0 if aucun_mot_cle else round(confiance, 3)

    explicite, relatif = _extraire_exercice(texte, question_norm)
    exercice = explicite
    exercice_implicite = relatif
    if exercice is None and relatif is not None:
        from datetime import datetime, timezone

        exercice = datetime.now(timezone.utc).year + relatif
        exercice_implicite = relatif

    communes = _trier_entites(
        [groupe.strip() for groupe in MOTIF_COMMUNE.findall(question_norm)]
    )
    types_prestation = _trier_entites(
        [groupe.strip() for groupe in MOTIF_TYPE_PRESTATION.findall(question_norm)]
    )

    mois = None
    correspondance = MOTIF_MOIS.search(question_norm)
    if correspondance:
        mois = MOIS_NOMMES.get(correspondance.group(1))

    resultat = IntentionQuery(
        question=texte,
        intention=intention,
        agregation=_detecter_agregation(question_norm),
        confiance=round(confiance, 3),
        scores=scores,
        exercice=exercice,
        exercice_implicite=exercice_implicite,
        communes=communes,
        situations=_extraire_situations(question_norm),
        types_prestation=types_prestation,
        mois=mois,
        mots_cles=_mots_significatifs(question_norm),
        aucun_mot_cle=aucun_mot_cle,
    )
    logger.info(
        "Question analysée : intention=%s agregation=%s confiance=%.3f exercice=%s",
        resultat.intention,
        resultat.agregation,
        resultat.confiance,
        resultat.exercice,
    )
    return resultat


def referentiel_intentions() -> dict[str, Any]:
    """Périmètre couvert par l'assistant, exposé par l'API."""
    return {
        "intentions": [
            {
                "code": code,
                "libelle": LIBELLES_INTENTIONS[code],
            }
            for code in INTENTIONS
        ],
        "regle": (
            "Les chiffres proviennent exclusivement du backend ; "
            "l'assistant ne calcule ni n'invente aucune valeur."
        ),
    }
