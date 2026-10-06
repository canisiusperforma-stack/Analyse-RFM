"""Étapes « Nettoyage » et « Découpage » du pipeline RAG.

Le nettoyage rend le texte interrogeable sans le déformer ; le découpage le
découpe en unités de sens indexables. Les deux sont ici parce qu'ils obéissent
à la même contrainte : **ne rien changer au sens**. Un texte administratif est
dense en nombres, en références d'articles et en sigles ; toute normalisation
hasardeuse y détruit une information. Chaque transformation ci-dessous ne touche
que la mise en forme, jamais les marqueurs porteurs de sens.

Nettoyage
    Unicode normalisé (NFC), espaces insécables ramenés à des espaces ordinaires,
    caractères de contrôle supprimés, groupes de milliers assemblés
    (« 1 000 000 » → « 1000000 »), césures de fin de ligne recollées
    (« phenomè- » + saut de ligne + « ne » → « phénomène »), sauts de ligne
    multiples réduits, espaces en fin de ligne retirés. Les nombres, montants,
    pourcentages, dates, matricules et références d'articles ne sont pas touchés :
    seule leur séparature typographique est remise en forme, jamais leur valeur.

Découpage
    Les paragraphes sont accumulés jusqu'à la taille cible. Un paragraphe plus
    long que cette taille est coupé **sur une frontière de phrase**, jamais au
    milieu d'un mot, afin qu'un morceau reste une unité cohérente. La taille cible
    du corps d'un morceau est `RAG_CHUNK_TAILLE - RAG_CHUNK_RECOUVREMENT` : la
    place du recouvrement est réservée d'emblée, si bien que deux morceaux
    consécutifs qui partagent `RAG_CHUNK_RECOUVREMENT` caractères — une question
    portant sur une phrase à cheval sur la frontière retrouve malgré tout le
    contexte — restent bornés par `RAG_CHUNK_TAILLE`.

Provenance
    Chaque morceau conserve la page et le titre de section dont il provient.
    C'est cette provenance qui permet de citer « p. 4 — Titre de section » plutôt
    qu'un identifiant opaque, et donc de rendre une réponse vérifiable.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Optional

from app.config import settings
from app.rag.document_loader import Bloc, DocumentExtrait
from app.rag.erreurs import ErreurDocumentaire
from app.utils.logging import get_logger

logger = get_logger(__name__)

#: Caractères de contrôle autorisés (retour à la ligne, tabulation).
CONTROLES_AUTORISES = {"\n", "\t"}

#: Espaces typographiques ramenés à une espace ordinaire.
ESPACES_SPECIAUX = {
    "\u00a0": " ",
    "\u202f": " ",
    "\u2009": " ",
    "\u2007": " ",
    "\u200b": "",
    "\ufeff": "",
    "\u200c": "",
    "\u200d": "",
}

#: Frontière de phrase : ponctuation de fin, espace, puis majuscule ou chiffre.
FRONTIERE_PHRASE = re.compile(r"(?<=[.!?…])[ \t]+(?=[\"«'(\u201c]?[A-ZÀ-Þ0-9])")

#: Paragraphe : une ou plusieurs lignes séparées par une ligne vide.
PARAGRAPHE = re.compile(r"\n[ \t]*\n+")

#: Séparateur de milliers français : « 1 000 000 ». La règle n'assemble qu'un
#: groupe d'exactement trois chiffres, suivi d'un caractère non chiffré, ce qui
#: laisse intacts les suites de nombres courts (« 12 34 56 ») et les années
#: énumérées (« exercices 2023 2024 »).
GROUPES_MILLIERS = re.compile(r"(?<=\d)[ \t]+(?=\d{3}(?!\d))")

#: Titre de section détecté dans un texte non structuré.
TITRE_MD = re.compile(r"^(#{1,6})\s+(.+?)\s*#*$")
TITRE_NUMERO = re.compile(
    r"^(?:(?:article|chapitre|section|annexe)\s+)?"
    r"(?:\d+|[IVXLC]+)[.)]?\s+\S.{0,110}$",
    re.IGNORECASE,
)
TITRE_MAJUSCULES = re.compile(r"^[A-ZÀ-Þ][A-ZÀ-Þ0-9 ,'\-()]{3,110}[.:]?$")


@dataclass
class Morceau:
    """Unité de texte indexable, avec sa provenance dans le document."""

    texte: str
    ordinal: int
    page: Optional[int] = None
    titre: Optional[str] = None
    debut_source: int = 0
    fin_source: int = 0

    @property
    def nb_caracteres(self) -> int:
        return len(self.texte)

    def reference(self) -> str:
        """Localisateur lisible, repris tel quel dans les citations."""
        elements = []
        if self.page is not None:
            elements.append(f"p. {self.page}")
        if self.titre:
            elements.append(self.titre)
        return " — ".join(elements) if elements else f"morceau {self.ordinal}"


# --- Nettoyage -------------------------------------------------------------


def _corriger_cesure(texte: str) -> str:
    """Recolle les mots coupés en fin de ligne (« institu-\\ntion »).

    Une césure est un trait d'union **immédiatement suivi d'un retour à la
    ligne**, dont la ligne suivante commence par une minuscule : c'est la
    signature du retour automatique à la ligne. Un tiret suivi d'un retour à la
    ligne et d'une majuscule reste un tiret ordinaire : la ligne suivante
    commence alors un nouvel énoncé.
    """
    return re.sub(r"(\w)-[ \t]*\n[ \t]*(?=[a-zà-ÿîôûéèêëç])", r"\1\n", texte)


def nettoyer(texte: str) -> str:
    """Normalise la mise en forme d'un texte sans en altérer le contenu."""
    if not texte:
        return ""

    resultat = unicodedata.normalize("NFC", texte)
    resultat = resultat.replace("\r\n", "\n").replace("\r", "\n")

    for caractere, remplacement in ESPACES_SPECIAUX.items():
        resultat = resultat.replace(caractere, remplacement)

    resultat = "".join(
        caractere
        for caractere in resultat
        if caractere in CONTROLES_AUTORISES
        or unicodedata.category(caractere) not in ("Cc", "Cf", "Co", "Cs")
    )

    # Les groupes de milliers sont assemblés avant toute réduction d'espaces :
    # « 1 000 000 » doit devenir « 1000000 » pour que le montant soit
    # retrouvable par une question qui écrit le chiffre sans séparateur. La
    # valeur n'est pas modifiée, seule la séparature typographique.
    resultat = GROUPES_MILLIERS.sub("", resultat)

    resultat = _corriger_cesure(resultat)
    resultat = re.sub(r"[ \t]+\n", "\n", resultat)
    resultat = re.sub(r"\n[ \t]+", "\n", resultat)
    resultat = re.sub(r"[ \t]{2,}", " ", resultat)
    resultat = re.sub(r"\n{3,}", "\n\n", resultat)
    resultat = re.sub(r"[ \t]{2,}", " ", resultat)

    return resultat.strip()


# --- Découpage -------------------------------------------------------------


def _est_titre(paragraphe: str) -> bool:
    """Un paragraphe court et isolé ressemble-t-il à un titre de section ?"""
    texte = paragraphe.strip()
    if not texte or "\n" in texte or len(texte) > 120:
        return False
    return bool(
        TITRE_MD.match(texte)
        or TITRE_NUMERO.match(texte)
        or TITRE_MAJUSCULES.match(texte)
    )


def _couper_phrase(texte: str, taille: int) -> list[str]:
    """Découpe un paragraphe trop long sur ses frontières de phrase.

    Le découpage progresse phrase par phrase tant qu'il reste de la place ; si
    une phrase unique dépasse la taille, elle est coupée sur une espace, ce qui
    garantit qu'aucun mot n'est tronqué en deux.
    """
    morceaux: list[str] = []
    restant = texte.strip()

    while len(restant) > taille:
        fenetre = restant[:taille]
        positions = [m.end() for m in FRONTIERE_PHRASE.finditer(fenetre)]
        if positions:
            coupe = positions[-1]
        else:
            espace = fenetre.rfind(" ")
            coupe = espace if espace > taille * 0.4 else len(fenetre)

        morceaux.append(restant[:coupe].strip())
        restant = restant[coupe:].strip()

    if restant:
        morceaux.append(restant)

    return [morceau for morceau in morceaux if morceau]


def _reculer_phrase(texte: str, recouvrement: int) -> str:
    """Suffixe de `texte` à préfixer au morceau suivant, aligné sur une phrase.

    Deux exigences tirent en sens opposé. Le recouvrement ne doit pas commencer
    au milieu d'une phrase, sans quoi l'enchaînement lu par le modèle serait
    incohérent. Mais il ne doit pas non plus être raccourci sous la valeur
    configurée : réduire la fenêtre à la dernière phrase fitte laisserait de côté
    la phrase qui chevauche la frontière, précisément celle que le recouvrement
    existe pour préserver.

    On recule donc jusqu'à la **première** frontière de la fenêtre, ce qui allonge
    le préfixe au lieu de l'amputer. Une frontière située exactement en fin de
    fenêtre est ignorée : elle ne laisserait qu'un préfixe vide. En l'absence de
    ponctuation — une table CSV, une liste — on recule jusqu'à la première espace,
    pour ne jamais couper un mot.

    Le résultat ne peut donc jamais dépasser `recouvrement` : on ne fait que
    retrancher un en-tête, jamais ajouter.
    """
    if not texte:
        return ""

    fenetre = texte[-recouvrement:]
    if not fenetre:
        return ""

    debut = next(
        (
            correspondance.end()
            for correspondance in FRONTIERE_PHRASE.finditer(fenetre)
            if correspondance.end() < len(fenetre)
        ),
        -1,
    )
    if debut < 0:
        espace = fenetre.find(" ")
        debut = espace + 1 if espace >= 0 else 0

    return fenetre[debut:].strip()


def _iterer_unites(blocs: list[Bloc]):
    """Produit (texte, page, titre) en assimilant les titres aux blocs voisins.

    Un titre isolé devient l'intitulé de la section qui suit au lieu d'être
    indexé comme s'il était une phrase : c'est ainsi que « Article 5 —
    Conditions d'octroi » se retrouve dans la citation du morceau qui traite
    réellement des conditions d'octroi.
    """
    titre_courant: Optional[str] = None

    for bloc in blocs:
        texte = (bloc.texte or "").strip()
        if not texte:
            continue

        if bloc.titre:
            titre_courant = bloc.titre

        if "\n" not in texte and _est_titre(texte):
            correspondance = TITRE_MD.match(texte)
            titre_courant = (
                correspondance.group(2).strip() if correspondance else texte
            )
            continue

        for paragraphe in PARAGRAPHE.split(texte):
            if paragraphe.strip():
                yield paragraphe, bloc.page, titre_courant


def decouper(
    document: DocumentExtrait,
    taille: Optional[int] = None,
    recouvrement: Optional[int] = None,
    taille_min: Optional[int] = None,
) -> list[Morceau]:
    """Découpe un document extrait en morceaux indexables.

    `taille` est la longueur maximale d'un morceau **recouvrement compris**, et
    non la taille du texte neuf : le corps d'un morceau est donc
    `taille - recouvrement`, si bien que le recouvrement appliqué entre deux
    morceaux consécutifs laisse la longueur finale bornée par `taille`.

    Le recouvrement ne s'applique qu'entre deux morceaux consécutifs d'un même
    document : un morceau ne doit jamais mêler la fin d'un texte au début d'un
    autre, sans quoi une citation attribuerait à un document une phrase de
    l'autre.
    """
    taille = taille or settings.RAG_CHUNK_TAILLE
    recouvrement = (
        recouvrement if recouvrement is not None else settings.RAG_CHUNK_RECOUVREMENT
    )
    taille_min = taille_min or settings.RAG_CHUNK_TAILLE_MIN
    recouvrement = max(0, min(recouvrement, max(taille - 1, 0)))

    #: Corps du morceau : la place du recouvrement est réservée d'emblée.
    corps = max(1, taille - recouvrement)

    morceaux: list[Morceau] = []
    ordinal = 0
    position_source = 0

    for texte_source, page, titre in _iterer_unites(document.blocs):
        texte = nettoyer(texte_source)
        if not texte:
            continue

        for portion in _couper_phrase(texte, corps):
            if not portion:
                continue

            debut = position_source
            position_source += len(portion)

            contenu = f"{titre}\n{portion}" if titre else portion

            # Un morceau trop court est rattaché au précédent plutôt que d'être
            # indexé seul : un fragment de vingt mots est rarement retrouvable.
            if (
                len(contenu) < taille_min
                and morceaux
                and morceaux[-1].titre == titre
                and len(morceaux[-1].texte) + len(portion) <= corps
            ):
                morceaux[-1].texte = f"{morceaux[-1].texte}\n{portion}".strip()
                morceaux[-1].fin_source = position_source
                continue

            ordinal += 1
            morceaux.append(Morceau(
                texte=contenu.strip(),
                ordinal=ordinal,
                page=page,
                titre=titre,
                debut_source=debut,
                fin_source=position_source,
            ))

    if recouvrement:
        _appliquer_recouvrement(morceaux, recouvrement, taille)

    if not morceaux:
        raise ErreurDocumentaire(
            "Aucun texte exploitable après nettoyage : le document ne produit "
            "aucun contenu indexable.",
            etapa="decoupage",
        )

    moyenne = sum(morceau.nb_caracteres for morceau in morceaux) // max(len(morceaux), 1)
    logger.info(
        "Découpage : %s morceau(s), %s caractère(s) au total, %s en moyenne",
        len(morceaux),
        sum(morceau.nb_caracteres for morceau in morceaux),
        moyenne,
    )
    return morceaux


def _appliquer_recouvrement(
    morceaux: list[Morceau],
    recouvrement: int,
    taille: int,
) -> None:
    """Recouvre chaque morceau du début du précédent.

    Un morceau déjà plus long que `taille` n'est pas allongé : on ne dépasse
    jamais la longueur maximale, et l'on ne tronque jamais un contenu pour le
    sake du mécanisme. C'est le cas d'une phrase unique plus longue qu'un
    morceau, qui reste entière.
    """
    for position in range(1, len(morceaux)):
        precedent = morceaux[position - 1]
        courant = morceaux[position]

        if precedent.titre != courant.titre or precedent.page != courant.page:
            continue

        if len(courant.texte) > taille:
            continue

        contexte = _reculer_phrase(precedent.texte, recouvrement)
        if not contexte:
            continue

        courant.texte = f"{contexte}\n{courant.texte}".strip()


def decouper_document(
    contenu: bytes,
    nom_fichier: str,
) -> tuple[DocumentExtrait, list[Morceau]]:
    """Enchaîne extraction, nettoyage et découpage (étapes 1 à 4 du pipeline)."""
    from app.rag.document_loader import extraire

    document = extraire(contenu, nom_fichier)
    morceaux = decouper(document)
    return document, morceaux


def statistiques(morceaux: list[Morceau]) -> dict[str, Any]:
    """Volume indexé, utile au compte rendu d'import et aux tests."""
    if not morceaux:
        return {"nb_morceaux": 0, "nb_caracteres": 0, "pages": [], "taille_moyenne": 0}
    pages = sorted({morceau.page for morceau in morceaux if morceau.page is not None})
    total = sum(morceau.nb_caracteres for morceau in morceaux)
    return {
        "nb_morceaux": len(morceaux),
        "nb_caracteres": total,
        "pages": pages,
        "taille_moyenne": total // len(morceaux),
    }
