"""Contrôle des chiffres annoncés par le modèle.

Deuxième rempart de la règle fondamentale, après le prompt. Le modèle peut
ignorer ses consignes : ce module, lui, ne cède pas. Il extrait chaque nombre
écrit dans la réponse et le rapproche des seules valeurs fournies par le
backend. Tout nombre non rattaché à une donnée autorisée est une invention et
fait échouer la validation.

Rapprochement
    Un nombre est autorisé s'il correspond à une valeur du backend, à la
    précision près de son écriture. La tolérance est celle de l'arrondi :
    un jeton à une décimale accepte un écart de 0,05. Le modèle peut donc
    arrondir, reformater (« 1 250 000 Ar », « 62,3 % », « 1,25 M ») sans
    jamais pouvoir produire une valeur absente des données.

Reformats tolérés
    Un nombre n'est rattaché au backend que s'il y figure tel quel, ou si
    l'écriture du modèle en explicite la conversion : abréviation de devise
    (« 1,25 M »), signe « % », « pour mille ». La conversion n'est jamais
    devinée, si bien qu'un « 1,25 M » ne peut pas valider un 1,25 Md. La
    valeur absolue d'un montant négatif est également admise, car les
    messages produits par le backend énoncent eux-mêmes les dépassements
    sous forme positive.

Exemptions
    Les nombres employés en numération (« les 3 axes à surveiller ») ne sont
    pas des données : ils sont tolérés lorsqu'ils sont suivis d'un nom
    d'énumération. Aucune donnée chiffrée métier n'est ainsi jamais acceptée
    par cette porte de sortie.

En cas d'échec, `assainir` masque les nombres fautifs et `assistant_service`
retombe sur une réponse construite par le code : l'utilisateur ne voit
jamais de chiffre non vérifié.

Limite assumée
    Le contrôle porte sur la valeur, non sur l'unité qui l'accompagne. Une
    proportion stockée à 0,6234 se valide par « 62,3 % », la conversion étant
    déduite de l'écriture ; en revanche « 6234 % » est refusé, car il
    désignerait 62,34. Repérer une unité mal appariée au sein d'une valeur
    par ailleurs exacte demanderait une analyse sémantique de chaque segment,
    au prix de faux positifs (« +250 % » est une variation légitime). C'est
    pourquoi le prompt interdit explicitement au modèle de convertir, et
    pourquoi la réponse est systématique rattachée à ses sources.
"""

from __future__ import annotations

import bisect
import math
import re
from dataclasses import dataclass, field
from typing import Any, Optional

from app.config import settings
from app.utils.logging import get_logger

logger = get_logger(__name__)

MOTIF_NOMBRE = re.compile(
    r"(?<![\w])"
    r"(?P<signe>[+-]?)"
    r"(?P<corps>"
    r"\d{1,3}(?:[.,]\d{3}){2,}(?:[.,]\d+)?"
    r"|\d{1,3}(?:[ \u00a0\u202f]\d{3})+(?:[.,]\d+)?"
    r"|\d+(?:[.,]\d+)?"
    r")"
    r"\s*(?P<suffixe>md|MD|Md|[kKmM])?"
    r"(?!\w)",
    re.VERBOSE,
)

MULTIPLICATEURS: dict[str, float] = {
    "k": 1_000.0,
    "m": 1_000_000.0,
    "md": 1_000_000_000.0,
}

ESPACES_SEPARATEURS = (" ", "\u00a0", "\u202f", "\u2009")

NOMBRE_ORDINAL_MAX = 12
SEUIL_LONGUEUR_MINIMALE = 0.6

NOUNS_ENUMERATION: frozenset[str] = frozenset(
    {
        # assistant analytique
        "axe", "axes", "point", "points", "element", "elements", "etape",
        "etapes", "partie", "parties", "volet", "volets", "recommandation",
        "recommandations", "categorie", "categories", "facteur", "facteurs",
        "critere", "criteres", "niveau", "niveaux", "suggestion",
        "suggestions", "priorite", "priorites", "consequence",
        "consequences", "risque", "risques", "indicateur", "indicateurs",
        "focus", "constat", "constats", "preoccupation", "preoccupations",
        # variantes accentuees des memes termes
        "étape", "étapes", "catégorie", "catégories", "critère", "critères",
        "priorité", "priorités", "conséquence", "conséquences", "préoccupation",
        "préoccupations",
        # chatbot documentaire : ce sont des dénombrements d'exigences, de
        # pièces ou de documents, jamais des valeurs mesurées
        "condition", "conditions", "cas", "piece", "pieces", "pièce",
        "pièces", "exigence", "exigences", "article", "articles",
        "document", "documents", "modalite", "modalites", "modalité",
        "modalités", "regle", "regles", "règle", "règles", "obligation",
        "obligations", "procedure", "procedures", "procédure", "procédures",
        "version", "versions", "faculte", "facultes", "faculté", "facultés",
        "crit", "ligne", "lignes", "rubrique", "rubriques", "chapitre",
        "chapitres", "etape", "etapes",
    }
)

MARQUEUR_MASQUE = "[valeur non vérifiée]"


@dataclass
class EcartNumerique:
    """Nombre écrit par le modèle sans correspondance dans les données."""

    valeur: float
    brut: str
    debut: int
    fin: int
    contexte: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "valeur": self.valeur,
            "ecrit": self.brut,
            "contexte": self.contexte,
        }


@dataclass
class ResultatValidation:
    """Verdict du contrôle numérique d'une réponse."""

    valide: bool = True
    total_chiffres: int = 0
    chiffres_verifies: list[dict[str, Any]] = field(default_factory=list)
    ecarts: list[EcartNumerique] = field(default_factory=list)
    exemptions: int = 0

    @property
    def nombre_ecarts(self) -> int:
        return len(self.ecarts)

    @property
    def taux_erreur(self) -> float:
        if not self.total_chiffres:
            return 0.0
        return round(len(self.ecarts) / self.total_chiffres, 4)

    def resume(self) -> dict[str, Any]:
        return {
            "conforme": self.valide,
            "chiffres_verifies": self.total_chiffres - self.nombre_ecarts,
            "chiffres_inventes": self.nombre_ecarts,
            "taux_erreur": self.taux_erreur,
            "exemptions_ordinales": self.exemptions,
            "detail": [ecart.to_dict() for ecart in self.ecarts[:20]],
        }


def _sans_separateurs(texte: str) -> str:
    for espace in ESPACES_SEPARATEURS:
        texte = texte.replace(espace, "")
    return texte


def _analyser_nombre(signe: str, corps: str, suffixe: str) -> Optional[tuple[float, int]]:
    """Convertit un nombre écrit en style français en (valeur, décimales)."""
    corps = corps.strip()
    if not corps:
        return None

    decoupe = re.split(r"[.,]", corps)
    if len(decoupe) >= 3 and all(len(morceau) == 3 for morceau in decoupe[1:]):
        numerique = "".join(decoupe)
        decimales = 0
    else:
        position = max(corps.rfind("."), corps.rfind(","))
        if position > 0:
            entiere = _sans_separateurs(corps[:position])
            partie = _sans_separateurs(corps[position + 1 :])
            if not entiere.isdigit() or (partie and not partie.isdigit()):
                return None
            decimales = len(partie)
            numerique = f"{entiere}.{partie}" if partie else entiere
        else:
            numerique = _sans_separateurs(corps)
            decimales = 0

    try:
        valeur = float(numerique)
    except ValueError:
        return None

    if signe == "-":
        valeur = -valeur
    multiplicateur = MULTIPLICATEURS.get((suffixe or "").lower())
    if multiplicateur:
        valeur *= multiplicateur
    return valeur, decimales


def _iterer_nombres(texte: str):
    for correspondance in MOTIF_NOMBRE.finditer(texte):
        groupes = correspondance.groupdict()
        analyse = _analyser_nombre(
            groupes["signe"] or "", groupes["corps"] or "", groupes["suffixe"] or ""
        )
        if analyse is None:
            continue
        valeur, decimales = analyse
        yield correspondance, valeur, decimales


def _est_numeration(texte: str, position: int) -> bool:
    """Vrai si le nombre sert à énumérer (« les 3 axes »)."""
    suite = texte[position : position + 40]
    mots = re.findall(r"[A-Za-zÀ-ÿ]+", suite.lower())[:2]
    return any(mot in NOUNS_ENUMERATION for mot in mots)


class IndexValeurs:
    """Ensemble des valeurs autorisées, interrogeable avec une tolérance."""

    def __init__(self) -> None:
        self._valeurs: list[float] = []
        self._origines: list[str] = []
        self._ajouts: set[tuple[float, str]] = set()

    def ajouter(self, valeur: float, origine: str) -> None:
        cle = (round(valeur, 10), origine)
        if cle in self._ajouts:
            return
        self._ajouts.add(cle)
        self._valeurs.append(valeur)
        self._origines.append(origine)

    def indexer_objet(self, donnees: Any, chemin: str = "") -> None:
        """Parcourt la charge utile et enregistre toutes les valeurs."""
        if isinstance(donnees, dict):
            for cle, valeur in list(donnees.items())[:500]:
                self.indexer_objet(valeur, f"{chemin}.{cle}" if chemin else str(cle))
            return
        if isinstance(donnees, (list, tuple)):
            for index, valeur in enumerate(list(donnees)[:500]):
                self.indexer_objet(valeur, f"{chemin}[{index}]")
            return
        if isinstance(donnees, bool) or donnees is None:
            return
        if isinstance(donnees, (int, float)):
            self._enregistrer(float(donnees), chemin)
            return
        if isinstance(donnees, str):
            for _, valeur, _ in _iterer_nombres(donnees):
                self._enregistrer(valeur, chemin or "texte")

    def _enregistrer(self, valeur: float, chemin: str) -> None:
        self.ajouter(valeur, chemin)
        if valeur < 0:
            self.ajouter(-valeur, f"{chemin} (valeur absolue)")

    def finaliser(self) -> None:
        couples = sorted(zip(self._valeurs, self._origines), key=lambda item: item[0])
        self._valeurs = [valeur for valeur, _ in couples]
        self._origines = [origine for _, origine in couples]

    def origine(self, valeur: float, decimales: int) -> Optional[str]:
        """Origine de la valeur si elle est autorisée à la précision donnée."""
        if not self._valeurs:
            return None
        tolerance = max(0.5 * 10 ** (-decimales), settings.LLM_TOLERANCE_NUMERIQUE / 1000)
        borne = bisect.bisect_left(self._valeurs, valeur - tolerance)
        while borne < len(self._valeurs) and self._valeurs[borne] <= valeur + tolerance:
            if abs(self._valeurs[borne] - valeur) <= tolerance:
                return self._origines[borne]
            borne += 1
        return None

    @property
    def taille(self) -> int:
        return len(self._valeurs)


def construire_index(faits: Any) -> IndexValeurs:
    """Construit l'index des valeurs autorisées à partir du backend."""
    index = IndexValeurs()
    index.indexer_objet(faits or {})
    index.finaliser()
    return index


def _contexte(texte: str, debut: int, fin: int, largeur: int = 45) -> str:
    gauche = max(0, debut - largeur)
    droite = min(len(texte), fin + largeur)
    extrait = texte[gauche:droite].replace("\n", " ").strip()
    return f"…{extrait}…"


def _candidats(
    correspondance: re.Match,
    texte: str,
    valeur: float,
    decimales: int,
) -> list[tuple[float, str, int]]:
    """Valeurs admissibles selon la façon dont le nombre est écrit.

    Une valeur n'est rattachée au backend que si elle y figure telle quelle,
    ou si l'écriture du modèle en explicite la conversion (abréviation
    « M », signe « % », « pour mille »). Aucune conversion n'est devinée :
    c'est ce qui empêche un « 1,25 M » de valider un 1,25 Md.

    Chaque candidat porte la **précision avec laquelle il doit être
    recherché**, et non celle du nombre écrit. C'est indispensable dès qu'une
    conversion intervient : le backend stocke un taux sous forme de fraction
    (0,784), et « 78 % » doit être cherché comme 0,78. Or la tolérance du
    validateur est une demi-unité de la dernière décimale — si elle restait
    mesurée sur le nombre écrit, « 85 % » donnerait 0,85 avec une tolérance de
    ±0,5, c'est-à-dire cinquante points de pourcentage : n'importe quel seuil
    proche d'un seuil connu aurait alors été accepté. Ce n'est pas une
    hypothèse, c'est le défaut que la fusion a mis au jour. La précision suit
    donc l'échelle, en gagnant autant de décimales que l'unité en introduit.
    """
    candidats: list[tuple[float, str, int]] = [(valeur, "valeur directe", decimales)]

    suffixe = (correspondance.group("suffixe") or "").lower()
    multiplicateur = MULTIPLICATEURS.get(suffixe)
    if multiplicateur:
        candidats.append((
            valeur * multiplicateur,
            f"abréviation « {suffixe} »",
            decimales + _decimales_du_facteur(abs(multiplicateur)),
        ))

    suite = texte[correspondance.end() : correspondance.end() + 12]
    if re.match(r"\s*%", suite):
        candidats.append((valeur / 100.0, "pourcentage", decimales + 2))
    elif re.match(r"\s*(?:‰|pour\s+mille)", suite, re.IGNORECASE):
        candidats.append((valeur / 1000.0, "pour mille", decimales + 3))
    return candidats


def _decimales_du_facteur(facteur: float) -> int:
    """Décimales gagnées par une conversion d'unité.

    `1e6` vaut trois ordres de grandeur, `1_000` deux. Un facteur qui n'est pas
    une puissance de dix exacte — une abréviation arrondie, par exemple — ne
    peut pas être décrit par un décalage de décimales ; on lui laisse alors la
    précision du nombre écrit, ce qui est le choix conservateur.
    """
    if facteur <= 0:
        return 0
    exposant = math.log10(facteur)
    arrondi = round(exposant)
    if abs(exposant - arrondi) > 1e-9:
        return 0
    return int(arrondi)


def valider_reponse(
    reponse: str,
    faits: Any,
    index: Optional[IndexValeurs] = None,
) -> ResultatValidation:
    """Vérifie que tous les chiffres de la réponse proviennent du backend."""
    texte = reponse or ""
    if not texte.strip():
        return ResultatValidation(valide=False, total_chiffres=0)

    reference = index if index is not None else construire_index(faits)
    resultat = ResultatValidation()

    for correspondance, valeur, decimales in _iterer_nombres(texte):
        resultat.total_chiffres += 1

        origine = None
        forme = "valeur directe"
        for candidat, libelle, precision in _candidats(
            correspondance, texte, valeur, decimales
        ):
            origine = reference.origine(candidat, precision)
            if origine is not None:
                forme = libelle
                break

        if origine is not None:
            resultat.chiffres_verifies.append({
                "ecrit": correspondance.group(0).strip(),
                "valeur": valeur,
                "origine": origine,
                "forme": forme,
            })
            continue

        if (
            decimales == 0
            and float(valeur).is_integer()
            and 1 <= valeur <= NOMBRE_ORDINAL_MAX
            and _est_numeration(texte, correspondance.end())
        ):
            resultat.exemptions += 1
            resultat.chiffres_verifies.append({
                "ecrit": correspondance.group(0).strip(),
                "valeur": valeur,
                "origine": "énumération",
            })
            continue

        resultat.ecarts.append(EcartNumerique(
            valeur=valeur,
            brut=correspondance.group(0).strip(),
            debut=correspondance.start(),
            fin=correspondance.end(),
            contexte=_contexte(texte, correspondance.start(), correspondance.end()),
        ))

    resultat.valide = not resultat.ecarts
    if not resultat.valide:
        logger.warning(
            "Réponse rejetée : %s chiffre(s) non autorisé(s) sur %s "
            "(valeurs autorisées indexées : %s)",
            resultat.nombre_ecarts,
            resultat.total_chiffres,
            reference.taille,
        )
    return resultat


def assainir(reponse: str, resultat: ResultatValidation) -> str:
    """Remplace les nombres non vérifiés par un marqueur explicite."""
    texte = reponse or ""
    if resultat.valide or not resultat.ecarts:
        return texte

    morceaux: list[str] = []
    curseur = 0
    for ecart in sorted(resultat.ecarts, key=lambda item: item.debut):
        if ecart.debut < curseur:
            continue
        morceaux.append(texte[curseur : ecart.debut])
        morceaux.append(MARQUEUR_MASQUE)
        curseur = ecart.fin
    morceaux.append(texte[curseur:])
    return "".join(morceaux)
