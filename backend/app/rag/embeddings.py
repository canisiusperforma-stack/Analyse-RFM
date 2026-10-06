"""Étape « Embeddings » du pipeline RAG : texte → vecteur comparable.

Deux vecteurs/textes du même document doivent être comparables d'un appel à
l'autre, d'un processus à l'autre, et après un redémarrage. Cette contrainte
dirige tout le choix technique : la fonction de vectorisation ne doit dépendre
d'aucun état mémorisé, d'aucun modèle téléchargé, d'aucun appel réseau.

Ce qui est retenu
    Des vecteurs de **n-grammes hachés** : le texte est découpé en mots et en
    bicharres, chaque n-gramme est envoyé dans une case d'un vecteur de
    `RAG_EMBED_DIM` dimensions par une fonction de hachage, la fréquence est
    comprimée logarithmiquement, puis le vecteur est normalisé. La similarité
    est le produit scalaire des vecteurs normalisés, soit le cosinus.

Pourquoi ce choix
    `scikit-learn` est déjà une dépendance du projet (`app.ml`), et son
    `HashingVectorizer` ne s'entraîne pas : aucun vocabulaire n'est appris, donc
    rien n'est à conserver ni à versionner, et un morceau indexé hier reste
    comparable à une question posée aujourd'hui. Les deux vecteurs de hachage
    qui composent l'embedding se complètent : les **mots** (uni- et bicharres)
    portent le sens, les **caractères** (3 à 5) rapprochent les variantes
    morphologiques et les fautes de frappe courantes dans une saisie
    administrative (« Execution » / « exécution », « benificiaire »).

Ce que ce choix ne fait pas
    Ce n'est pas un modèle neuronal : il n'a aucune notion de synonymie. Une
    question qui écrit « exécution » ne retrouvera pas un document qui écrit
    « realisation » si les formes littérales diffèrent trop. C'est pourquoi la
    recherche est **hybride** (`app.rag.retriever`) et non purement vectorielle,
    et pourquoi le seuil de pertinence est un paramètre explicite
    (`RAG_SEUIL_PERTINENCE`) : mieux vaut déclarer une information introuvable
    que produire une réponse sans source.

Changer de modèle
    `RAG_EMBED_MODELE` nomme la fonction employée. En ajouter une consiste à
    écrire une fonction de même signature et à l'enregistrer dans `FONCTIONS` :
    le reste de la chaîne (indexation, recherche, citation) n'a pas à changer.
    Un changement de modèle impose de réindexer les documents, la dimension
    pouvant différer — d'où le contrôle de dimension à la lecture.
"""

from __future__ import annotations

import hashlib
from typing import Callable, Optional, Sequence

import numpy as np
from sklearn.feature_extraction.text import HashingVectorizer

from app.config import settings
from app.utils.logging import get_logger

logger = get_logger(__name__)

#: Le vecteur est normé sur la sphère unité : le cosinus est alors le produit
#: scalaire, sans division à chaque comparaison.
VECTEUR_MOTS_FRAGMENTS = 0.5
VECTEUR_CARACTERES_FRAGMENTS = 0.5

_cache: dict[int, tuple[HashingVectorizer, HashingVectorizer]] = {}


def _vecteurs(dimension: int) -> tuple[HashingVectorizer, HashingVectorizer]:
    """Construit (et mémorise) les deux vectoriseurs pour une dimension donnée.

    `alternate_sign=False` : toutes les composantes restent positives. Le signe
    négatif de l'algorithme de *hashing trick* original est un moyen de réduire
    les collisions, mais il ferait osciller le produit scalaire autour de zéro
    pour deux textes sans rapport, et interpréterait à tort « aucun mot commun »
    comme « similarité négative ». Un seuil de pertinence doit signifier
    « pertinent » et non « pas opposé ».
    """
    if dimension in _cache:
        return _cache[dimension]

    demi = max(dimension // 2, 32)

    mots = HashingVectorizer(
        n_features=demi,
        analyzer="word",
        ngram_range=(1, 2),
        lowercase=True,
        strip_accents="unicode",
        alternate_sign=False,
        norm=None,
        token_pattern=r"(?u)\b\w[\w'-]*\b",
    )
    caracteres = HashingVectorizer(
        n_features=demi,
        analyzer="char_wb",
        ngram_range=(3, 5),
        lowercase=True,
        alternate_sign=False,
        norm=None,
    )

    _cache[dimension] = (mots, caracteres)
    return mots, caracteres


def _compresser(matrice: np.ndarray) -> np.ndarray:
    """Compression logarithmique puis normalisation en norme 2.

    La compression logarithmique tempère l'effet des répétitions : un terme
    présent dix fois ne pèse pas dix fois un terme présent une fois, sans quoi
    un en-tête de page répété dominerait le score d'un morceau qui répond
    réellement à la question.

    Aucune protection n'est nécessaire autour de `log1p` : la fonction est
    définie et exacte en zéro, qu'elle renvoie `0`. Seule la normalisation
    demande un plancher, pour qu'une ligne entièrement nulle — un morceau vide
    ou un texte réduit à des ponctuations — reste à un vecteur nul au lieu de
    produire des `NaN` qui se propageraient au classement.
    """
    resultat = matrice.astype(np.float64, copy=True)
    np.log1p(resultat, out=resultat)
    normes = np.linalg.norm(resultat, axis=1, keepdims=True)
    return resultat / np.maximum(normes, 1e-12)


def vectoriser(texte: str, dimension: Optional[int] = None) -> np.ndarray:
    """Vectorise un texte unique en vecteur dense de dimension `dimension`."""
    return vectoriser_plusieurs([texte], dimension=dimension)[0]


def vectoriser_plusieurs(
    textes: Sequence[str],
    dimension: Optional[int] = None,
) -> np.ndarray:
    """Vectorise un lot de textes en une matrice dense.

    La forme renvoyée est `(len(textes), dimension)`. Un lot vide renvoie une
    matrice de forme `(0, dimension)`, ce qui évite au code appelant de traiter
    à part le cas d'aucun candidat.
    """
    dimension = dimension or settings.RAG_EMBED_DIM
    mots, caracteres = _vecteurs(dimension)

    if not textes:
        return np.zeros((0, dimension), dtype=np.float32)

    if VECTEUR_MOTS_FRAGMENTS + VECTEUR_CARACTERES_FRAGMENTS <= 0:
        raise ValueError(
            "La pondération des fragments de vecteur ne peut pas être nulle ou négative."
        )

    matrice = np.hstack([
        _compresser(mots.transform(list(textes)).toarray().astype(np.float64))
        * VECTEUR_MOTS_FRAGMENTS,
        _compresser(caracteres.transform(list(textes)).toarray().astype(np.float64))
        * VECTEUR_CARACTERES_FRAGMENTS,
    ])

    # Chaque fragment sort de `_compresser` de norme 1 ; le poids appliqué puis
    # cette division ramènent le vecteur combiné à la norme 1. Sans cette
    # division, le produit scalaire de `similarite` vaudrait deux fois le cosinus
    # et le seuil de pertinence perdrait sa signification.
    matrice = matrice.astype(np.float32)
    return matrice / np.sqrt(
        VECTEUR_MOTS_FRAGMENTS**2 + VECTEUR_CARACTERES_FRAGMENTS**2
    )


def similarite(requete: np.ndarray, matrice: np.ndarray) -> np.ndarray:
    """Similarité cosinus entre un vecteur de requête et une matrice de morceaux.

    Les deux entrées étant normées, le produit scalaire donne le cosinus. La
    fonction reste correcte pour une matrice vide, auquel cas elle renvoie un
    tableau vide.
    """
    if matrice.size == 0:
        return np.zeros(0, dtype=np.float32)
    if requete.ndim == 1:
        requete = requete.reshape(1, -1)
    if requete.shape[1] != matrice.shape[1]:
        raise ValueError(
            f"Dimensions incompatibles : requête {requete.shape[1]}, "
            f"morceaux {matrice.shape[1]}. Le modèle d'embeddings a peut-être "
            "changé : les documents doivent être réindexés."
        )
    return (matrice @ requete.reshape(-1)).astype(np.float32)


def empreinte(texte: str) -> str:
    """Empreinte stable d'un texte, pour détecter un contenu déjà indexé."""
    return hashlib.sha256(texte.encode("utf-8")).hexdigest()


def decrire() -> dict[str, object]:
    """Description du modèle employé, exposée par le référentiel de l'API."""
    return {
        "modele": settings.RAG_EMBED_MODELE,
        "dimension": settings.RAG_EMBED_DIM,
        "technique": "n-grammes hachés (mots 1-2, caractères 3-5), "
        "fréquence compressée logarithmiquement, vecteur normalisé",
        "distance": "cosinus (produit scalaire de vecteurs normés)",
        "entrainement": "aucun : la fonction est déterministe et sans état",
    }


#: Le module a d'abord exposé ces deux fonctions sous l'orthographe
#: « vecteuriser ». Des appelants existants — dont `retriever` — la reprennent
#: encore : les alias sont conservés pour ne pas rompre ces appels, les
#: définitions ci-dessus font foi.
vecteuriser = vectoriser
vecteuriser_plusieurs = vectoriser_plusieurs


#: Tableau des fonctions de vectorisation disponibles, indexé par nom.
FONCTIONS: dict[str, Callable[..., np.ndarray]] = {
    "local-hash": vectoriser_plusieurs,
}
