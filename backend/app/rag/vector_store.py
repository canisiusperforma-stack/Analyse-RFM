"""Étape « Vector Store » : conservation des vecteurs et recherche par similarité.

MongoDB sert à la fois de dépôt des vecteurs et de **point d'application du
filtrage d'accès**. C'est un choix délibéré : la clause `$or` construite par
`app.models.document.filtre_acces_documents` entre dans la requête, si bien
qu'un morceau interdit n'est jamais transmis au processus qui classe les
résultats. Le classement s'exécute donc sur des candidats déjà autorisés — il ne
peut pas « remonter » vers un document interdit, puisqu'il ne le voit pas.

Sélection des candidats
    Deux régimes, pour rester exact sur les volumes gérables et borné au-delà :

    - corpus autorisé inférieur à `RAG_RECHERCHE_CANDIDATS` : **tous** les
      morceaux autorisés sont chargés, le classement est donc exact ;
    - au-delà : une présélection lexicale MongoDB (`$text`) ramène le corpus à
      `RAG_RECHERCHE_CANDIDATS` candidats avant vectorisation.

    Le second régime est un compromis assumé — un classement exhaustif exigerait
    de charger des centaines de milliers de vecteurs — et il est signalé dans le
    résultat, via `exhaustif`, pour que l'appelant puisse en tenir compte.

Le classement
    Cosinus via produit scalaire de vecteurs normés. Cette recherche est
    purement vectorielle : la fusion avec un score lexical, et le seuil de
    pertinence, relèvent de `app.rag.retriever`, qui connaît la question.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Optional

import numpy as np
from pymongo import ASCENDING, DESCENDING

from app.config import settings
from app.database import obtenir_database
from app.models.document import document_visible, filtre_acces_documents
from app.repositories.document_repository import COLLECTION_MORCEAUX
from app.utils.logging import get_logger

logger = get_logger(__name__)

#: Champs ramenés d'un candidat : le strict nécessaire au classement puis à la
#: citation, rien de plus.
PROJECTION_CANDIDAT = {
    "document_id": 1,
    "ordinal": 1,
    "contenu": 1,
    "titre": 1,
    "page": 1,
    "vecteur": 1,
    "confidentialite": 1,
    "roles_autorises": 1,
    "utilisateurs_autorises": 1,
    "nom_fichier": 1,
    "type_mime": 1,
    "created_at": 1,
}

#: Termes retenus pour la présélection lexicale : alphanumériques et apostrophes
#: internes, les seuls caractères qu'une recherche MongoDB accepte sans syntaxe
#: particulière. Les autres (guillemets, tirets, astérisques, `OR`) seraient
#: interprétés comme des opérateurs.
TERMES_RECHERCHE = re.compile(r"[\w']+", re.UNICODE)


@dataclass
class Candidat:
    """Morceau autorisé, vectorisé et prêt à être classé."""

    document_id: str
    ordinal: int
    contenu: str
    titre: Optional[str]
    page: Optional[int]
    vecteur: np.ndarray
    confidentialite: str
    roles_autorises: list[str] = field(default_factory=list)
    utilisateurs_autorises: list[str] = field(default_factory=list)
    nom_fichier: Optional[str] = None
    type_mime: Optional[str] = None
    score_dense: float = 0.0

    def autorise(self, utilisateur: Optional[dict[str, Any]]) -> bool:
        """Revérification d'accès, appliquée au résultat et non à la requête.

        La clause Mongo est la barrière principale ;         ce contrôle est la seconde.
        Il existe parce qu'une erreur dans la construction du filtre — un champ
        mal orthographié, une condition oubliée — ne doit pas suffire à
        divulguer un extrait. Coût : une comparaison par candidat.
        """
        return document_visible(
            {
                "confidentialite": self.confidentialite,
                "roles_autorises": self.roles_autorises,
                "utilisateurs_autorises": self.utilisateurs_autorises,
            },
            utilisateur,
        )


def construire_filtre(
    utilisateur: Optional[dict[str, Any]],
    documents: Optional[list[Any]] = None,
) -> dict[str, Any]:
    """Assemble le filtre d'accès et le périmètre documentaire demandé.

    Les deux conditions sont combinées par `$and` : la clause d'accès reste
    indivisible, et un périmètre restreint ne peut pas l'affaiblir. Sans `$and`,
    un `documents` vide produirait un filtre `{}` — c'est-à-dire aucun contrôle
    d'accès du tout.
    """
    conditions: list[dict[str, Any]] = [filtre_acces_documents(utilisateur)]

    if documents:
        from bson import ObjectId

        identifiants = []
        for identifiant in documents:
            try:
                identifiants.append(
                    identifiant if isinstance(identifiant, ObjectId)
                    else ObjectId(str(identifiant))
                )
            except Exception:  # noqa: BLE001
                logger.warning("Identifiant de document ignoré : %r", identifiant)
        if not identifiants:
            return {"$and": conditions + [{"_id": {"$in": []}}]}
        conditions.append({"document_id": {"$in": identifiants}})

    return {"$and": conditions} if len(conditions) > 1 else conditions[0]


def _termes_recherche(texte: str) -> list[str]:
    """Termes de la question retenus pour la présélection lexicale."""
    return [terme.lower() for terme in TERMES_RECHERCHE.findall(texte or "")][:24]


async def _candidats(
    filtre: dict[str, Any],
    termes: list[str],
    limite: int,
) -> tuple[list[dict[str, Any]], bool, int]:
    """Récupère les candidats et indique si le corpus a été parcouru en entier."""
    db = obtenir_database()
    collection = db[COLLECTION_MORCEAUX]

    total = await collection.count_documents(filtre)
    if total == 0:
        return [], True, 0

    if total <= limite:
        curseur = collection.find(filtre, PROJECTION_CANDIDAT).limit(limite)
        return [candidat async for candidat in curseur], True, total

    if not termes:
        logger.warning(
            "Corpus de %s morceaux, question sans terme lexical exploitable : "
            "aucune présélection possible, aucun candidat retenu.",
            total,
        )
        return [], False, total

    recherche = " ".join(termes)
    try:
        curseur = (
            collection.find(
                {"$and": [filtre, {"$text": {"$search": recherche}}]},
                {**PROJECTION_CANDIDAT, "score": {"$meta": "textScore"}},
            )
            .sort([("score", {"$meta": "textScore"})])
            .limit(limite)
        )
        return [candidat async for candidat in curseur], False, total
    except Exception as erreur:  # noqa: BLE001
        logger.warning(
            "Présélection lexicale impossible (%s) : repli sur les %s morceaux "
            "les plus récents parmi les documents autorisés.",
            erreur,
            limite,
        )
        curseur = (
            collection.find(filtre, PROJECTION_CANDIDAT)
            .sort("created_at", DESCENDING)
            .limit(limite)
        )
        return [candidat async for candidat in curseur], False, total


def _vers_matrice(
    documents: list[dict[str, Any]],
) -> tuple[np.ndarray, list[dict[str, Any]]]:
    """Assemble la matrice de vecteurs et signale les dimension incohérentes.

    Un morceau indexé avec un autre modèle d'embeddings est écarté plutôt que
    d'être tronqué ou complété : il produirait un score faux. Un changement de
    `RAG_EMBED_DIM` impose donc de réindexer, ce que le compte rendu d'import
    signale.
    """
    reutilisables: list[dict[str, Any]] = []
    dimension_attendue = settings.RAG_EMBED_DIM
    for document in documents:
        vecteur = document.get("vecteur")
        if not isinstance(vecteur, list) or not vecteur:
            logger.warning(
                "Morceau %s/%s sans vecteur exploitable : ignoré.",
                document.get("document_id"),
                document.get("ordinal"),
            )
            continue
        if len(vecteur) != dimension_attendue:
            logger.error(
                "Morceau %s/%s : vecteur de dimension %s, modèle courant en attend "
                "%s. Le document doit être réindexé.",
                document.get("document_id"),
                document.get("ordinal"),
                len(vecteur),
                dimension_attendue,
            )
            continue
        reutilisables.append(document)

    if not reutilisables:
        return np.zeros((0, dimension_attendue), dtype=np.float32), []

    matrice = np.asarray(
        [document["vecteur"] for document in reutilisables], dtype=np.float32
    )
    return matrice, reutilisables


async def chercher(
    vecteur_requete: np.ndarray,
    utilisateur: Optional[dict[str, Any]],
    texte_requete: str = "",
    limite: Optional[int] = None,
    documents: Optional[list[Any]] = None,
) -> tuple[list[Candidat], dict[str, Any]]:
    """Classe les morceaux autorisés par similarité avec la question.

    Renvoie les candidats classés et un compte rendu d'exécution : corpus
    autorisé, caractère exhaustif de la présélection, dimension des vecteurs.
    """
    limite = limite or settings.RAG_RECHERCHE_CANDIDATS
    filtre = construire_filtre(utilisateur, documents)
    termes = _termes_recherche(texte_requete)

    documents_candidats, exhaustif, total = await _candidats(filtre, termes, limite)

    compte_rendu: dict[str, Any] = {
        "corpus_autorise": total,
        "candidats_examines": len(documents_candidats),
        "preselection_exhaustive": exhaustif,
        "dimension": settings.RAG_EMBED_DIM,
    }

    if not documents_candidats:
        return [], compte_rendu

    matrice, retenus = _vers_matrice(documents_candidats)
    if not retenus:
        return [], compte_rendu

    scores = (matrice @ vecteur_requete.reshape(-1)).astype(np.float32)
    compte_rendu["candidats_retenus"] = len(retenus)

    resultats: list[Candidat] = []
    retires = 0
    for document, score in zip(retenus, scores):
        candidat = Candidat(
            document_id=str(document.get("document_id", "")),
            ordinal=int(document.get("ordinal", 0)),
            contenu=document.get("contenu") or "",
            titre=document.get("titre"),
            page=document.get("page"),
            vecteur=np.asarray(document.get("vecteur"), dtype=np.float32),
            confidentialite=document.get("confidentialite") or "interne",
            roles_autorises=list(document.get("roles_autorises") or []),
            utilisateurs_autorises=[
                str(identifiant)
                for identifiant in (document.get("utilisateurs_autorises") or [])
            ],
            nom_fichier=document.get("nom_fichier"),
            type_mime=document.get("type_mime"),
            score_dense=round(float(score), 6),
        )

        if not candidat.autorise(utilisateur):
            retires += 1
            continue

        resultats.append(candidat)

    if retires:
        # Ne devrait jamais se produire : la clause d'accès est déjà dans la
        # requête. Le journaliser signale une divergence entre les deux
        # barrières plutôt que de la laisser passer en silence.
        logger.error(
            "%s morceau(x) eliminated by the second access check although the "
            "query filter allowed them : review filtre_acces_documents.",
            retires,
        )
        compte_rendu["retires_par_verification"] = retires

    resultats.sort(key=lambda candidat: candidat.score_dense, reverse=True)
    return resultats, compte_rendu


async def compter_autorises(utilisateur: Optional[dict[str, Any]]) -> int:
    """Volume de morceaux réellement accessibles à cet utilisateur."""
    db = obtenir_database()
    return await db[COLLECTION_MORCEAUX].count_documents(
        construire_filtre(utilisateur)
    )


async def purger_document(document_id: Any) -> int:
    """Retire les morceaux d'un document, en appliquant le même filtre d'accès."""
    from bson import ObjectId

    from app.repositories.document_repository import supprimer_morceaux

    try:
        cible = (
            document_id if isinstance(document_id, ObjectId)
            else ObjectId(str(document_id))
        )
    except Exception:  # noqa: BLE001
        return 0
    return await supprimer_morceaux(cible)


async def documents_autorises(
    utilisateur: Optional[dict[str, Any]],
    limite: int = 50,
    saut: int = 0,
) -> list[dict[str, Any]]:
    """Liste les documents visibles, pour l'écran « Mes documents »."""
    from app.repositories.document_repository import lister_documents

    return await lister_documents(
        filtre=filtre_acces_documents(utilisateur), limite=limite, saut=saut
    )


#: Index ascendant retenu par défaut, explicité pour le tri des listes.
TRI_PAR_DEFAUT = ASCENDING
