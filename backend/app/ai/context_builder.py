"""Assemblage du contexte unique transmis au modèle de langage.

Ce module est la charnière entre les deux sources d'information. Il produit
l'objet described au §7 du cahier des charges — `ContexteAssistant` — et
**rien d'autre** : aucune interrogation, aucun calcul, aucun appel réseau. Sa
seule responsabilité est de gathered ce que le backend sait déjà, dans une
forme que le modèle ne peut pas outrepasser.

Pourquoi un contexte, plutôt qu'un accès
    Le modèle ne reçoit aucun handle sur MongoDB, ni sur l'index vectoriel, ni
    sur une fonction du backend. Il reçoit un objet figé. Il peut donc
    reformuler ce qu'il voit, mais il ne peut pas élargir sa fenêtre : pour
    obtenir une information absente du contexte, il n'a aucun moyen de la
    demander. C'est une garantie **structurelle**, là où une consigne dans un
    prompt n'est qu'une promesse que le modèle peut ne pas tenir.

Deux blocs, et non un
    `data_context` porte les chiffres, `document_context` porte les règles.
    Les séparer ne relève pas de la présentation : c'est ce qui permet ensuite
    à `app.ai.response_validator` de contrôler qu'un chiffre cité provient du
    premier bloc et qu'une règle affirmée provient du second. Un contexte
    unique et indifférencié rendrait ce contrôle impossible, puisque toute
    valeur deviendrait admissible dès lors qu'elle figure quelque part.

Anonymisation des extraits
    Un document SRB peut contenir, parapluiement de sa procédure, une pièce
    type remplie d'exemples : un matricule, un nom, une date de naissance. Ces
    informations ne servent jamais à répondre à une question sur la procédure
    et n'ont aucun intérêt pour l'utilisateur qui la pose. Elles sont donc
    masquées **avant** toute transmission, y compris avant retour dans la
    réponse de l'API — masquées donc aussi pour l'utilisateur autorisé, ce qui
    est ici le bon compromis : la confidentialité prime sur la reproduction
   Integrity d'un exemple.

    Le masquage est volontairement étroit. Un filtre trop agressif
    — « six mois » pour un matricule à six chiffres, « cent mille » pour un
    montant — rendrait l'extrait illisible et ferait perdre la seule chose
    utile qu'il contient. Chaque motif vise donc une **suite de chiffres d'une
    longueur discriminante**, ou un champ explicitement nommé.
"""

from __future__ import annotations

import re
from typing import Any, Iterable, Optional

from app.ai.indicator_service import ABSENT, ResultatStructure, UNITE_TEXTE
from app.ai.response_validator import IndexValeurs, construire_index
from app.config import settings
from app.rag.retriever import Source
from app.schemas.assistant import (
    ContexteAssistant,
    ContexteDocument,
    ContexteDonnees,
    MesureContexte,
    RouteQuery,
)
from app.utils.logging import get_logger

logger = get_logger(__name__)

#: Remplace toute donnée personnelle détectée. La formulation est neutre et
#: n'indique pas la nature de la valeur retirée : un masque qui annonçait
#: « nom masqué » signalerait à l'utilisateur qu'un nom figurait dans le
#: document, ce qui est déjà une information.
MASQUE = "[donnée sensible retirée]"

#: Motifs d'identification personnelle, appliqués aux extraits documentaires.
#:
#: - `coordonnées` : courriel et numéro de téléphone malgache.
#: - `date de naissance` : une date précédée d'un libellé explicite.
#: - `nom de personne` : précédé d'une civilité.
#: - `champ nommé` : un libellé d'identité suivi de sa valeur. Plus précis que
#:   le motif générique suivant, il saisit les identifiants alphanumériques
#:   (`CIN AB123456`) et les matricules écrits par groupes.
#: - `identifiant long` : **neuf chiffres ou plus, sans séparateur**. La
#:   restriction au séparateur est délibérée, et elle a été motivée par une
#:   correction : un motif plus permissif, qui admettait les espaces, masquait
#:   « 1 250 000 Ar » — c'est-à-dire le montant lui-même. Or un montant est
#:   précisément ce que l'extrait existe pour transmettre ; le neutraliser
#:   rendrait l'extrait inexploitable. Un identifiant écrit « 123 456 789 »
#:   échappe donc à ce motif. C'est le prix à payer, cette écriture étant
#:   indistinguable d'un nombre ; il est rattrapé dès qu'un libellé le nomme,
#:   par le motif `champ nommé`.
#:
#: L'ordre des motifs est significatif, pas anodin : les plus spécifiques
#: passent en premier. Dans l'autre sens, le motif « neuf chiffres ou plus »
#: absorbait « +261321122233 » avant que le motif téléphone ne pût le voir,
#: ne laissant qu'un « + » nu — trace duolveil de l'erreur, et indice fiable
#: que le masque avait été appliqué au mauvais endroit. Un motif large placé
#: avant un motif étroit rend le second inopérant ; c'est l'inverse qui est
#: correct.
MOTIFS_IDENTIFIANTS: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        # Indicatif malgache 020/021 pour la fixe, 032/033/034/036/037/038
        # pour le mobile ; une écriture qui ne retenait que les 02x laissait
        # passer tous les portables, qui sont les plus courants.
        re.compile(
            r"(?<![\d.])(?:\+261[ . -]?|0)(?:2[01]|3[2-9])"
            # Le découpage des groupes varie selon la saisie (2-2-3-2, 2-2-2-2,
            # sans séparateur). Exiger une répartition fixe laissait passer la
            # moitié des numéros.
            r"(?:[ . -]?\d){7,8}(?![\d])"
        ),
        MASQUE,
    ),
    (
        re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"),
        MASQUE,
    ),
    (
        re.compile(
            r"\bdate\s+de\s+naissance\b\s*[:\s]*(?:le\s+)?[0-3]?\d[/-][01]?\d"
            r"[/-]\d{2,4}",
            re.IGNORECASE,
        ),
        MASQUE,
    ),
    (
        re.compile(
            r"\b(?:M\.|Mr|Monsieur|Mme|Madame|Mlle|Mademoiselle)\s+"
            r"[A-ZÀ-Ý][\wÀ-ÿ'’-]+(?:\s+[A-ZÀ-Ý][\wÀ-ÿ'’-]+)?"
        ),
        MASQUE,
    ),
    (
        re.compile(
            r"\b(?:matricule|nir|nin|cip|cin|cni|num[eé]ro\s+d['’]?identit[ée]"
            r"|num[eé]ro\s+de\s+piece|card[ée]?\s+d['’]?identit[ée]|"
            r"compte\s+bancaire|rib|iban)\b\s*[:\s]*[A-Z0-9][A-Z0-9./-]{2,}",
            re.IGNORECASE,
        ),
        MASQUE,
    ),
    (
        re.compile(
            r"(?<![\d.,+])\d{9,}(?![\d])"
            # Un nombre aussi long suivi d'une unité monétaire ou d'un
            # pourcentage est un montant, pas un identifiant : « 100000000 Ar »
            # est un plafond budgétaire. Sans cette garde, le masque avalerait
            # les montants que les documents ont précisément pour fonction de
            # fixer.
            r"(?!\s*(?:Ar\b|ariary\b|MGA\b|FM\b|%|pour\s?cent\b))"
        ),
        MASQUE,
    ),
)


def rediger(texte: str) -> str:
    """Masque les identifiants personnels d'un extrait documentaire.

    Fonction **non destructive pour la règle de calcul** : elle ne touche ni
    aux montants écrits avec séparateurs (« 1 250 000 Ar »), ni aux années, ni
    aux pourcentages. Elle ne modifie que les suites de chiffres longues et les
    champs explicitement nommés.
    """
    resultat = texte or ""
    for motif, remplacement in MOTIFS_IDENTIFIANTS:
        resultat = motif.sub(remplacement, resultat)
    return resultat


def _mesures_contexte(resultat: ResultatStructure) -> list[MesureContexte]:
    return [
        MesureContexte(
            cle=mesure.cle,
            libelle=mesure.libelle,
            valeur=mesure.valeur,
            unite=mesure.unite,
            valeur_affichee=mesure.to_dict()["valeur_affichee"],
        )
        for mesure in resultat.mesures
    ]


def _exercice_de(resultat: ResultatStructure) -> Optional[int]:
    if resultat.sources:
        exercice = resultat.sources[0].get("exercice")
        if exercice is not None:
            try:
                return int(exercice)
            except (TypeError, ValueError):
                return None
    return None


def construire_contexte_donnees(
    resultat: Optional[ResultatStructure],
    periode: Optional[int] = None,
) -> Optional[ContexteDonnees]:
    """Transforme le résultat structuré du calcul en bloc « chiffres ».

    Renvoie `None` — et non un bloc vide — lorsqu'aucun calcul n'a eu lieu.
    La distinction importe : un bloc vide pourrait se lire comme un résultat à
    zéro, alors que l'absence de bloc signifie qu'aucune source n'a été
    interrogée.
    """
    if resultat is None:
        return None

    principale = next(
        (mesure for mesure in resultat.mesures if mesure.unite != UNITE_TEXTE),
        None,
    )

    return ContexteDonnees(
        indicateur=resultat.indicateur,
        libelle=resultat.libelle,
        periode=periode if periode is not None else _exercice_de(resultat),
        statut=resultat.statut,
        valeur_principale=principale.valeur if principale else None,
        unite=principale.unite if principale else resultat.unite,
        calcul=resultat.note,
        source="MongoDB",
        source_detail=list(resultat.sources),
        mesures=_mesures_contexte(resultat),
        tableau=resultat.tableau,
        absence=resultat.absence,
    )


def construire_contexte_documents(
    sources: Iterable[Source],
) -> list[ContexteDocument]:
    """Transforme des extraits retenus en bloc « règles documentaires ».

    L'ordre est celui de la pertinence : il est conservé tel quel, car
    l'étiquette `[S1]` attribuée ici est celle que le modèle devra citer, et
    qu'un contrôle ultérieur vérifiera. Réordonner après coup romprait ce
    contrat.
    """
    contexte: list[ContexteDocument] = []
    for source in sources:
        contexte.append(
            ContexteDocument(
                etiquette=source.etiquette,
                document=source.nom_fichier or "document",
                document_id=source.document_id,
                page=source.page,
                reference=source.reference(),
                titre=source.titre,
                confidentialite=source.confidentialite,
                score=source.score,
                extrait=rediger(source.contenu),
            )
        )
    return contexte


def limites_du_contexte(
    resultat: Optional[ResultatStructure],
    documents: list[ContexteDocument],
    route: RouteQuery,
) -> list[str]:
    """Limites que la réponse doit signaler, déduites de ce qui a été trouvé.

    Les produire ici, et non dans le prompt, évite que le modèle décide
    lui-même ce qui mérite d'être signalé. Une limite énoncée par le code est
    vérifiable ; une limite déduite par le modèle ne l'est pas.
    """
    limites: list[str] = []

    if route.requiert_donnees:
        if resultat is None:
            limites.append(
                "Aucune source de données n'a pu être interrogée pour cette "
                "question : aucun chiffre n'est donc communiqué."
            )
        elif resultat.statut == ABSENT:
            limites.append(
                "Les données nécessaires à cet indicateur sont absentes pour "
                "la période demandée : aucune valeur n'est estimée."
            )

    if route.requiert_documents:
        if not settings.RAG_ENABLED:
            limites.append(
                "La recherche documentaire est désactivée sur ce déploiement : "
                "aucun document n'a été consulté."
            )
        elif not documents:
            limites.append(
                "Aucun extrait de document autorisé ne correspond à cette "
                "question : aucune règle n'est donc citée."
            )

    if route.requiert_donnees and route.requiert_documents and documents and resultat:
        if resultat.statut == ABSENT:
            limites.append(
                "La comparaison n'a pas pu être établie : les chiffres "
                "observés manquent, seules les règles documentaires sont "
                "restituées."
            )
        elif route.periode is None:
            limites.append(
                "L'exercice de référence n'a pas été imposé par l'utilisateur."
            )

    return limites


def construire_contexte(
    route: RouteQuery,
    resultat: Optional[ResultatStructure] = None,
    sources: Optional[Iterable[Source]] = None,
    limites_collecte: Optional[Iterable[str]] = None,
) -> ContexteAssistant:
    """Assemble le contexte unique, toutes sources confondues.

    Chaque bloc n'est présent que s'il a été réellement alimenté. Un contexte
    qui porterait un bloc vide laisserait croire à une recherche effectuée sans
    résultat — ce qui n'est pas la même chose qu'une recherche non menée.

    `limites_collecte` reçoit les motifs d'absence que l'orchestrateur
    connaît seul, parce qu'ils dépendent de la tentative de collecte : RAG
    désactivé, permission refusée, recherche menée sans résultat. Ils sont
    transmis ici plutôt que fusionnés après coup pour que les limites du
    contexte restent produites à un seul endroit, et pour qu'une limite ne
    puisse être énoncée deux fois sous deux formulations.
    """
    documents = (
        construire_contexte_documents(sources)
        if route.requiert_documents and sources
        else []
    )
    donnees = (
        construire_contexte_donnees(resultat, route.periode)
        if route.requiert_donnees and resultat is not None
        else None
    )

    limites = limites_du_contexte(resultat, documents, route)
    for limite in limites_collecte or ():
        # Une limite déjà énoncée n'est pas répétée : le même fait peut être
        # connu par deux voies (bloc absent, donc motif calculé) et par une
        # seule (motif transmis). Le dire deux fois ferait croire à deux
        # problèmes distincts.
        if limite not in limites:
            limites.append(limite)

    contexte = ContexteAssistant(
        question=route.question,
        intent=route.intent,
        data_context=donnees,
        document_context=documents,
        limites=limites,
    )

    logger.info(
        "Contexte assemblé : route=%s, mesures=%s, extraits=%s, limites=%s",
        route.intent,
        len(donnees.mesures) if donnees else 0,
        len(documents),
        len(contexte.limites),
    )
    return contexte


def index_valeurs_autorisees(contexte: ContexteAssistant) -> IndexValeurs:
    """Index des seules valeurs que la réponse a le droit de citer.

    C'est le point de bascule de tout le dispositif. Le contrôle numérique
    (`app.ai.response_validator`) ne confronte la réponse qu'aux valeurs de cet
    index : un chiffre absent d'ici est une invention, qu'il vienne du backend
    ou des documents.

    Réunir les deux sources dans **un seul** index est indispensable. Avec deux
    index distincts — l'un pour les données, l'autre pour les documents — il
    faudrait choisir lequel appliquer, et tout choix serait arbitraire : on
    autoriserait soit un seuil jeté par un document à valider un chiffre de la
    base, soit un total de la base à valider une valeur affirmée par un
    document. Les deux ouvrent une voie à l'invention.

    Le contexte est indexé et non le `resultat` brut : il ne contient que ce
    qui doit être citable, jamais les valeurs intermédiaires de calcul. Un
    chiffre absent du contexte mais présent dans les faits bruts ne peut donc
    pas être cité — c'est exactement le comportement voulu.

Enfin, l'index n'admet que des valeurs **produites par le backend** :
    pour un extrait, son contenu, son nom de fichier et sa page — pas son score
    de pertinence. Ce n'est pas une précaution de principe, c'est un défaut qui
    a été constaté : le score (0,82) s'y retrouvait, et la conversion
    « 85 % → 0,85 » que fait le validateur s'appuyait alors dessus pour valider
    un seuil **inventé**. Un artefact de recherche n'est pas une information :
    il décrit la qualité d'une sélection, jamais son contenu, et il n'a donc
    aucune légitimité à valider une affirmation.
    """
    charge: dict[str, Any] = {"intent": contexte.intent}

    if contexte.data_context is not None:
        donnees = contexte.data_context
        charge["donnees"] = {
            "indicateur": donnees.indicateur,
            "periode": donnees.periode,
            "valeur_principale": donnees.valeur_principale,
            "mesures": [mesure.model_dump() for mesure in donnees.mesures],
            "tableau": donnees.tableau,
        }

    if contexte.document_context:
        # L'identifiant et la localisation entrent dans l'index, pas seulement le
        # contenu : le format de citation prescrit par `prompt_fusion` est
        # « `[S1] decret-2024-001.pdf, page 4` ». Sans cela, le numéro d'année
        # porté par un nom de fichier serait rejeté comme un chiffre inventé
        # alors qu'il est la provenance même de l'extrait. Ces valeurs sont
        # bornées à ce que le backend a lui-même produit — nom de fichier,
        # numéro de page — et ne peuvent donc pas servir à valider une
        # affirmation de valeur.
        charge["documents"] = {
            document.etiquette: {
                "document": document.document,
                "page": document.page,
                "extrait": document.extrait,
            }
            for document in contexte.document_context
        }

    index = construire_index(charge)
    logger.info(
        "Index des valeurs autorisées : %s valeurs (%s mesures, %s extraits)",
        index.taille,
        len(contexte.data_context.mesures) if contexte.data_context else 0,
        len(contexte.document_context),
    )
    return index


def resume_pour_api(contexte: ContexteAssistant) -> dict[str, Any]:
    """Version sérialisable du contexte, pour le journalisation et l'API."""
    return contexte.model_dump(mode="json")