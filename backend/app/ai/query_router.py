"""Routeur de questions : DATA, RAG, DATA_RAG ou INCONNUE.

Ce module est le **chef d'orchestre** du besoin. Il ne produit aucun chiffre,
n'interroge ni MongoDB, ni le vector store, ni le modèle de langage : il se
borne à décider *quel chemin minimal* une question mérite, et à nommer ce qu'il
faudrait savoir pour l'emprunter.

Pourquoi la classification se fait sans modèle
    Un routeur nourri d'un LLM ne serait pas auditable : il produirait une
    étiquette dont personne ne pourrait dire à quoi elle correspond, et dont
    l'erreur se traduirait par une requête inutile — voire par une source
    manquante. Ici, chaque décision est la sortie d'une somme de motifs pondérés
    dont les tables sont dans ce fichier, et le résultat est validé par un
    schéma Pydantic (`app.schemas.assistant.RouteQuery`) qui refuse toute
    incohérence entre le chemin annoncé et les sources demandées.

    Le modèle n'intervient qu'ensuite, pour rédiger une réponse à partir d'un
    résultat déjà calculé. Il ne choisit jamais la source.

Deux tables, et pourquoi elles sont distinctes
    La difficulté n'est pas de reconnaître « procédure » comme un mot
    documentaire — c'est de reconnaître que **« Quelle est la procédure de
    remboursement ? » n'est pas une question de données**, malgré le mot
    « remboursement » qu'elle contient. L'inverse est tout aussi vrai :
    « le niveau d'exécution observé respecte-t-il les règles des documents ? »
    est une question de données *et* de documents, alors qu'elle contient les
    mêmes mots.

    Un lexique unique ne distingue pas ces cas. Deux tables le font :

    **Noyau documentaire** — ce qui *décrit l'objet même* de la demande : une
    procédure, une règle, un critère, une instruction, un dispositif. Sa
    présence fait basculer en RAG, car une procédure ne se calcule pas : elle se
    lit. Le mot « remboursement » qui l'accompagne désigne le **thème** de la
    procédure, pas une quantité demandée.

    **Croisement** — ce qui **exige** un référentiel : « conforme », «
    respecte », « prévu par », « correspond à ». Ces verbes présupposent une
    norme : ils sont sans réponse tant que les deux termes — l'observé et la
    norme — n'ont pas été réunis. Leur présence, combinée à un indicateur
    effectivement identifiable, suffit à produire DATA_RAG.

Saturer l'indice plutôt que le sommer
    Les indices sont ramenés par `1 - exp(-poids / k)` et non par une
    division. Une somme brute n'est pas comparable à un seuil : « combien de
    bénéficiaires » et « procédure de remboursement » contiendraient des
    scores sans signification commune. La forme saturante, elle, donne 0 à
    l'absence, tend vers 1 sans jamais l'atteindre, et surtout est **monotone
    et bornée** : doubler les occurrences d'un motif double l'indice, ce qui
    permet de régler le seuil une fois pour toutes au lieu de le recalibrer à
    chaque ajout de terme.

Ambiguïté
    « Quel est le taux d'exécution ? » est une question recevable, mais
    impropre : le taux d'exécution de quel exercice ? Le routeur ne choisit
    pas d'année à la place de l'utilisateur. Il signale
    `besoin_clarification`, et l'orchestrateur transforme ce signal en question
    de précision. Choisir 2025 parce que c'est le plus récent reviendrait à
    répondre à une autre question que celle posée — une faute silencieuse, donc
    la pire.

    La demande de précision est **limitée** aux indicateurs explicitement
    bornés à un exercice (`INDICATEURS_BORNES_A_UN_EXERCICE`). Les indicateurs
    de population décrivent un état et se lisent sans année ; exiger un exercice
    pour « combien de bénéficiaires ? » serait une formalité sans information
    ajoutée.
"""

from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Optional

from app.ai import indicator_service, query_analyzer
from app.ai.query_analyzer import IntentionQuery
from app.config import settings
from app.schemas.assistant import RouteQuery
from app.utils.logging import get_logger

logger = get_logger(__name__)

# --- Chemins ----------------------------------------------------------------

ROUTE_DATA = "DATA"
ROUTE_RAG = "RAG"
ROUTE_DATA_RAG = "DATA_RAG"
ROUTE_INCONNUE = "INCONNUE"

ROUTES = (ROUTE_DATA, ROUTE_RAG, ROUTE_DATA_RAG, ROUTE_INCONNUE)

LIBELLES_ROUTES: dict[str, str] = {
    ROUTE_DATA: "Données RFM de la plateforme",
    ROUTE_RAG: "Documents autorisés du SRB",
    ROUTE_DATA_RAG: "Données RFM et documents du SRB",
    ROUTE_INCONNUE: "Hors périmètre des sources disponibles",
}

#: Ce que chaque chemin interroge, dans l'ordre d'appel. Cette table est la
#: traduction exécutable du §15 du cahier des charges : elle est la seule
#: autorité sur ce qu'un chemin coûte, l'orchestrateur n'en déduisant rien
#: par lui-même.
CHEMINS: dict[str, tuple[str, ...]] = {
    ROUTE_DATA: ("mongodb",),
    ROUTE_RAG: ("vectorstore", "llm"),
    ROUTE_DATA_RAG: ("mongodb", "vectorstore", "llm"),
    ROUTE_INCONNUE: (),
}

#: Cible de la forme saturante. Fixée à 3.0 : un motif de poids 3 — un seul
#: « procédure », un seul « conforme » — atteint l'indice 0.63, nettement au
#:-dessus des seuils par défaut, tandis que deux motifs faibles totalisent 0.5.
#: Ce calibrage rend le réglage du seuil insensible à la façon dont les poids
#: ont été choisis.
SATURATION = 3.0


# --- Lexique documentaire ---------------------------------------------------

#: **Noyau documentaire** — l'objet même de la demande. Poids fort : chacun de
#: ces termes suffit, seul, àOrient la question vers les documents.
NOYAU_DOCUMENTAIRE: tuple[tuple[str, int], ...] = (
    (r"procedures?", 4),
    (r"regles?", 4),
    (r"criteres?", 4),
    (r"modalites?", 4),
    (r"instructions?", 4),
    (r"directives?", 4),
    (r"circulaires?", 4),
    (r"arretes?", 4),
    (r"dispositifs?", 4),
    (r"demarches?", 3),
    (r"formalites?", 3),
    (r"manuels?", 3),
    (r"guides?", 3),
    (r"referentiels?", 3),
    (r"reglementations?", 3),
    (r"reglementaires?", 3),
    (r"cadres? (?:de |du )?(?:reglementaire|juridique|legislatif|normatif)", 4),
    (r"textes? (?:de |d' ?)?(?:reference|reglementaire|officiel)", 4),
    (r"(?:en |dans le |dans l')?(?:vigueur|application)", 4),
    (r"(?:th[èe]mes?|chapitres?|rubriques?) (?:de |d' ?)?(?:la |l' ?)?"
     r"(?:procedure|reglementation|instruction)", 4),
    (r"etapes? (?:de |de la |du )?(?:procedure|demarche|traitement)", 3),
    # La formulation usuelle de cette question est « quelles pièces faut-il
    # fournir », où l'auxiliaire s'intercale entre le nom et le verbe. La forme
    # « pièces à fournir » ne couvre donc que la variante la moins naturelle, et
    # « quelles pièces faut-il fournir » — qui ne contient aucun terme
    # documentaire par ailleurs — tombait en DATA sans indicateur, donc sans
    # réponse. Les auxiliaires sont énumérés plutôt que tolérés par un motif
    # générique : « pièce » seul ne doit pas suffire, et un intervalle de mots
    # libres finirait par capturer des questions de données.
    (r"pieces? (?:a |faut il |doit on |doivent (?:ils|elles) |"
     r"est il necessaire de )"
     r"(?:fournir|justifier|joindre|presenter|transmettre|deposer)", 4),
    # Forme adjectivale, sans verbe : « quelles pièces justificatives sont
    # exigées ? » ne contient ni « à fournir » ni « à joindre ».
    (r"pieces? (?:justificatives?|requises?|necessaires?|completes?)", 4),
    (r"agrement", 4),
    (r"conditions? (?:d' |de )?(?:eligibilite|admission|octroi|remboursement)", 4),
    (r"comment (?:faire|proceder|demander|obtenir)", 3),
    (r"quels? (?:sont|documents?|textes?)", 2),
    (r"de quoi (?:se compose|compose|parle)", 2),
)

#: `REFERENCE_IMPLICITE` — la question désigne des documents sans dire
#: clairement lequel. Poids faible : « le document » est aussi le nom que
#: l'utilisateur donne au dossier de remboursement, et une mention isolée ne
#: suffit pas à faire basculer la question vers les documents.
REFERENCE_IMPLICITE: tuple[tuple[str, int], ...] = (
    (r"documents?", 3),
    (r"documentation", 3),
    (r"note (?:de |d' ?)?(?:service|circulaire)", 3),
    (r"instructifs?", 3),
    (r"lois?", 2),
    (r"decrets?", 2),
    (r"lois? et (?:reglements|decrets)", 3),
)

#: **Croisement** — le verbe qui exige un référentiel. Ces formes supposent une
#: norme, donc les deux termes de la comparaison.
CROISEMENT: tuple[tuple[str, int], ...] = (
    (r"conforme?s?\b", 4),
    (r"conforme a|conforme aux|conformes a|conformes aux", 5),
    (r"respect\w*\s+(?:il\s+|elle\s+|ils\s+|elles\s+)?"
     r"(?:a|aux|le|la|les|t il|t elle|les regles|l obligation)", 5),
    (r"prevu\w*\s+(?:par|dans|aux)", 5),
    (r"prescrit\w*\s+(?:par|aux)", 5),
    (r"correspond\w*\s+(?:il\s+|a|aux|avec)", 4),
    (r"aligne\w*\s+(?:sur|avec)", 4),
    (r"verifie\w*\s+(?:sur|que|si)", 4),
    (r"prevoir\w*\s+(?:par|dans)", 4),
    (r"(?:telle|tel) que (?:prevue|prescrite|prevu|prescrit)", 4),
    (r"compare\w*\s+\w+\s+(?:avec|aux|a|par rapport)", 5),
    (r"par rapport aux (?:regles|criteres|dispositions)", 5),
    (r"ce que disent|ce que prevoit|ce que disent les documents", 5),
    (r"prevu par les documents|prevue par les documents", 5),
)

#: **Demande de chiffre** — ce qui distingue « quel montant ? » (une
#: grandeur) de « quel document ? » (une référence). Sert à basculer un
#: énoncé documentaire qui porte aussi une grandeur en DATA_RAG.
DEMANDE_CHIFFRE: tuple[tuple[str, int], ...] = (
    (r"taux\w*", 2),
    (r"montants?", 2),
    (r"combien", 3),
    (r"quel nombre|quelle nombre|nombre de", 2),
    (r"quantit\w*", 2),
    (r"volumes?", 1),
    (r"evolution\w*|tendanc\w*", 2),
    (r"moyenn\w*", 2),
    (r"repartition\w*", 2),
    (r"total\w*", 1),
    (r"somme\w*", 2),
    (r"cumul\w*", 2),
    (r"part\w*", 1),
    (r"cout\w*|depense\w*", 1),
    (r"surplus|decouvert|deficit|epargne", 2),
)


def _compiler(table: tuple[tuple[str, int], ...]) -> tuple[tuple[re.Pattern[str], int], ...]:
    return tuple(
        (re.compile(r"\b(?:" + motif + r")\b", re.IGNORECASE), poids)
        for motif, poids in table
    )


MOTIFS_NOYAU = _compiler(NOYAU_DOCUMENTAIRE)
MOTIFS_REFERENCE = _compiler(REFERENCE_IMPLICITE)
MOTIFS_CROISEMENT = _compiler(CROISEMENT)
MOTIFS_CHIFFRE = _compiler(DEMANDE_CHIFFRE)


# --- Indicateurs bornés à un exercice ---------------------------------------

#: Indicateurs dont la valeur n'a de sens que rapportée à un exercice : sans
#: année, « le taux d'exécution » et « le taux d'exécution de 2023 » sont deux
#: questions différentes, et le routeur ne peut pas trancher à la place de
#: l'utilisateur. Les indicateurs de population en sont exclus : ils décrivent
#: un état de la file, se lisent sans année, et exiger un exercice reviendrait à
#: demander une information qui n'apporte rien.
INDICATEURS_BORNES_A_UN_EXERCICE = frozenset(
    code
    for code in indicator_service.INDICATEURS_PAR_CODE
    if indicator_service.INDICATEURS_PAR_CODE[code].module
    in ("budget", "analyses", "previsions", "anomalies")
)

#: Étiquettes de clarification. Une seule par famille d'indicateur : la
#: question doit porter sur ce qui manque, pas sur l'indicateur identifié.
PREFIXE_CLARIFICATION = "Pour quel exercice"


# --- Normalisation ----------------------------------------------------------


def _normaliser(texte: str) -> str:
    """Minuscules, sans accents, ponctuation réduite à des espaces."""
    sans_accents = unicodedata.normalize("NFKD", (texte or "").lower())
    sans_accents = "".join(
        caractere
        for caractere in sans_accents
        if not unicodedata.combining(caractere)
    )
    return re.sub(r"[^a-z0-9]+", " ", sans_accents).strip()


def _indice(poids_total: float) -> float:
    """Rame un cumul de poids vers l'intervalle [0, 1[.

    `1 - exp(-poids / SATURATION)` vaut 0 sans motif, 0.63 pour un motif de
    poids 3, et tend vers 1 sans jamais l'atteindre. La borne ouverte vers 1
    est volontaire : elle garantit qu'aucune combinaison de motifs ne produit
    un indice indiscernable d'une certitude.
    """
    if poids_total <= 0:
        return 0.0
    return round(1.0 - math.exp(-poids_total / SATURATION), 4)


def _cumuler(
    question_norm: str,
    table: tuple[tuple[re.Pattern[str], int], ...],
) -> tuple[float, list[str]]:
    """Somme les poids des motifs trouvés et retient les termes reconnus."""
    poids_total = 0.0
    termes: list[str] = []
    for motif, poids in table:
        trouves = motif.findall(question_norm)
        if not trouves:
            continue
        poids_total += poids * len(trouves)
        for trouve in trouves:
            terme = _normaliser(str(trouve))
            if terme and terme not in termes:
                termes.append(terme)
    return poids_total, termes


# --- Décision ----------------------------------------------------------------


@dataclass
class Decision:
    """Décision du routeur et éléments d'analyse qui l'ont produite.

    L'intention de `query_analyzer` est conservée ici pour n'être calculée
    qu'une fois : l'orchestrateur la réutilise telle quelle, ce qui garantit que
    la question effectivement posée à la base est exactement celle qui a été
    routée.
    """

    route: RouteQuery
    intention: IntentionQuery
    indicateur: Optional[indicator_service.DefinitionIndicateur] = None
    indices: dict[str, float] = field(default_factory=dict)


def _question_clarification(libelle: str) -> str:
    """Formulation de la demande de précision sur l'exercice.

    Le libellé de l'indicateur est nommé pour que l'utilisateur sache *ce qui*
    doit être précisé : il ne s'agit pas de reformuler sa question, mais de
    choisir laquelle des questions en attente il retient.

    Le libellé est mis en tête, suivi de la question, et aucun article n'est
    nécessaire entre les deux. La raison est qu'aucun article ne peut être
    déduit du libellé : « Montants exécutés » est pluriel, « Population
    recensée » féminin, « Âge moyen » masculin élidé — et le genre ne se déduit
    pas d'un suffixe, puisque « Prévision de consommation » et « Solde
    budgétaire » se terminent tous deux par « on » et « e » sans être de même
    accord. Une liste d'exceptions serait fausse dès qu'un libellé changerait, et
    son absence produirait « connaître taux d'exécution budgétaire » : une
    phrase machine, mais tout de même une phrase.

    La tournure retenue est donc correcte pour tout libellé, sans exception à
    tenir. Le groupe nominal en tête de phrase ne demande pas d'article, et la
    question porte sur ce qui doit être précisé plutôt que sur la grandeur.
    """
    if not libelle:
        return f"{PREFIXE_CLARIFICATION} ?"
    minuscule = PREFIXE_CLARIFICATION[0].lower() + PREFIXE_CLARIFICATION[1:]
    return f"{libelle} : {minuscule} ?"


def classifier(
    question: str,
    exercice_impose: Optional[int] = None,
) -> Decision:
    """Classe une question et renvoie la décision complète du routeur.

    `exercice_impose` est la période fournie par l'appelant. Elle n'est jamais
    déduite : elle lève une ambiguïté que le routeur ne sait pas lever seul, et
    cette distinction est ce qui distingue « le taux d'exécution en 2025 » de
    « le taux d'exécution ».
    """
    texte = (question or "").strip()

    # L'analyse d'intention existante est réutilisée telle quelle : elle porte
    # déjà les dix intentions de domaine, l'extraction des entités et le
    # discernement des agrégations. Le routeur ne la réimplémente pas, il
    # s'y branche.
    intention = query_analyzer.analyser_question(texte)
    question_norm = _normaliser(texte)

    indicateur = indicator_service.identifier(intention)

    # « Possible » et « identifié » sont deux notions distinctes, et les
    # confondre ferait rater des questions mixtes. Une question peut relever
    # du domaine des données sans qu'aucun indicateur précis ne soit désigné :
    # « le niveau d'exécution observé » est de l'exécution budgétaire, mais le
    # motif exact du taux n'y figure pas. Exiger un indicateur nommé ferait
    # tomber cette question en RAG alors qu'elle est manifestement chiffrée —
    # et perdrait sa partie calculable.
    #
    # La consequence est reportée au moment utile : si aucun indicateur n'est
    # effectivement désigné, `indicator_service.resoudre` marque le résultat
    # absent en indiquant qu'aucun indicateur ne correspond. La branche
    # documentaire n'est pas perdue pour autant.
    donnees_possibles = intention.est_dans_perimetre()

    poids_noyau, termes_noyau = _cumuler(question_norm, MOTIFS_NOYAU)
    poids_reference, termes_reference = _cumuler(question_norm, MOTIFS_REFERENCE)
    poids_croisement, termes_croisement = _cumuler(question_norm, MOTIFS_CROISEMENT)
    poids_chiffre, termes_chiffre = _cumuler(question_norm, MOTIFS_CHIFFRE)

    noyau = poids_noyau > 0
    reference = poids_reference > 0
    croisement = poids_croisement > 0
    indice_rag = _indice(poids_noyau * 2 + poids_reference)

    # --- Choix du chemin ---------------------------------------------------
    if not noyau and not reference and not donnees_possibles:
        intent = ROUTE_INCONNUE
        raison = (
            "Aucun terme documentaire et aucun indicateur de la plateforme "
            "ne sont reconnus dans la question."
        )
    elif noyau and not croisement and not poids_chiffre:
        # « Quelle est la procédure de remboursement ? » — le mot «
        # remboursement » est le thème de la procédure, pas une grandeur
        # demandée : le noyau documentaire l'emporte.
        intent = ROUTE_RAG
        raison = (
            "La demande porte sur l'objet d'un texte (noyau documentaire : "
            f"{', '.join(termes_noyau[:3])}) sans grandeur ni comparaison."
        )
    elif croisement and donnees_possibles:
        # Le croisement est *lui-même* une référence : « conforme », « respecte »,
        # « prévu par » présupposent une norme. Exiger en plus un terme
        # documentaire nommé écartait ces questions de leur partie calculable —
        # « Le taux d'exécution respecte-t-il le seuil du texte ? » ne contient
        # ni « procédure » ni « document », et tombait en DATA en perdant
        # l'exposé du seuil que seule une recherche documentaire peut fournir.
        # Cette branche applique donc la règle énoncée en tête de module.
        intent = ROUTE_DATA_RAG
        raison = (
            "La question rapproche un chiffre calculé par la plateforme d'un "
            "référentiel documentaire"
            + (
                f" (croisement : {', '.join(termes_croisement[:2])})"
                if termes_croisement
                else ""
            )
            + "."
        )
    elif poids_chiffre and donnees_possibles and (noyau or reference):
        intent = ROUTE_DATA_RAG
        raison = (
            "La question porte sur "
            + (
                "un texte ("
                f"{', '.join(termes_noyau[:2])})"
                if noyau
                else "les documents ("
                f"{', '.join(termes_reference[:2])})"
            )
            + " tout en demandant une grandeur calculable par la plateforme "
            f"({', '.join(termes_chiffre[:2])})."
        )
    elif donnees_possibles:
        intent = ROUTE_DATA
        raison = (
            (
                f"Indicateur identifié : {indicateur.libelle}. "
                if indicateur is not None
                else f"Domaine de données reconnu : {intention.libelle}. "
            )
            + "Aucun terme documentaire ne justifie la recherche dans les "
            "documents."
        )
    elif noyau or reference:
        intent = ROUTE_RAG
        raison = (
            "La question porte sur les documents autorisés"
            f" ({', '.join((termes_noyau + termes_reference)[:3])}), sans "
            "indicateur calculable."
        )
    else:
        intent = ROUTE_INCONNUE
        raison = "Aucun indicateur de la plateforme ne correspond à cette question."

    # La fusion peut être coupée par la configuration : le routeur retombe alors
    # sur le chemin historique, et la branche documentaire devient
    # inexistante. Ce comportement est preferable à un refus, pour que
    # ASSISTANT_FUSION_ENABLED=false restaure exactement l'assistant d'avant.
    if not settings.ASSISTANT_FUSION_ENABLED and intent in (
        ROUTE_RAG,
        ROUTE_DATA_RAG,
    ):
        if donnees_possibles:
            intent = ROUTE_DATA
            raison += " Fusion désactivée : chemin retenu limité aux données."
        elif intent == ROUTE_RAG:
            intent = ROUTE_INCONNUE
            raison += " Fusion désactivée : aucun indicateur disponible."

    # --- Ambiguïté sur la période ------------------------------------------
    besoin_clarification = False
    question_clarification = None
    parametres_manquants: list[str] = []

    periode = exercice_impose if exercice_impose is not None else intention.exercice
    if (
        settings.ASSISTANT_CLARIFICATION
        and intent in (ROUTE_DATA, ROUTE_DATA_RAG)
        and indicateur is not None
        and indicateur.code in INDICATEURS_BORNES_A_UN_EXERCICE
        and periode is None
    ):
        besoin_clarification = True
        question_clarification = _question_clarification(indicateur.libelle)
        parametres_manquants.append("exercice")

    route = RouteQuery(
        question=texte,
        intent=intent,
        indicateur=indicateur.code if indicateur is not None else None,
        libelle_indicateur=indicateur.libelle if indicateur is not None else None,
        periode=periode,
        categorie=intention.intention if intention.est_dans_perimetre() else None,
        type_analyse=intention.agregation,
        requiert_donnees=intent in (ROUTE_DATA, ROUTE_DATA_RAG),
        requiert_documents=intent in (ROUTE_RAG, ROUTE_DATA_RAG),
        confiance=round(
            min(
                1.0,
                max(
                    intention.confiance,
                    indice_rag,
                    0.0 if indicateur is not None else 0.0,
                ),
            ),
            3,
        )
        if intent != ROUTE_INCONNUE
        else 0.0,
        raison=raison,
        scores={
            "donnees": round(intention.confiance, 4),
            "documents": indice_rag,
            "noyau_documentaire": round(_indice(poids_noyau), 4),
            "croisement": round(_indice(poids_croisement), 4),
            "grandeur": round(_indice(poids_chiffre), 4),
        },
        besoin_clarification=besoin_clarification,
        question_clarification=question_clarification,
        parametres_manquants=parametres_manquants,
        indices_documentaires=(termes_noyau + termes_reference + termes_croisement)[:8],
    )

    logger.info(
        "Route %s (confiance %.2f) — indicateur=%s periode=%s — noyau=%s "
        "croisement=%s grandeur=%s — clarification=%s",
        intent,
        route.confiance,
        route.indicateur,
        route.periode,
        round(_indice(poids_noyau), 3),
        round(_indice(poids_croisement), 3),
        round(_indice(poids_chiffre), 3),
        besoin_clarification,
    )
    return Decision(
        route=route,
        intention=intention,
        indicateur=indicateur,
        indices={
            "noyau": poids_noyau,
            "reference": poids_reference,
            "croisement": poids_croisement,
            "chiffre": poids_chiffre,
            "index_rag": indice_rag,
        },
    )


def router(
    question: str,
    exercice: Optional[int] = None,
) -> RouteQuery:
    """Raccourci : renvoie uniquement le schéma Pydantic de la décision."""
    return classifier(question, exercice_impose=exercice).route


def chemin_de(intent: str) -> tuple[str, ...]:
    """Services à interroger pour un chemin, dans l'ordre."""
    return CHEMINS.get(intent, ())


def referentiel_routes() -> dict[str, object]:
    """Périmètre de routage exposé par l'API.

    L'interface s'en sert pour expliquer à l'utilisateur *pourquoi* une
    question a suivi tel chemin, et pour annoncer les questions qu'elle sait
    traiter. Exposer les tables de motifs serait inutile ; exposer les chemins
    et leur coût, non.
    """
    return {
        "chemins": [
            {
                "code": code,
                "libelle": LIBELLES_ROUTES[code],
                "services": list(CHEMINS[code]),
            }
            for code in ROUTES
        ],
        "seuils": {
            "documents": settings.ASSISTANT_ROUTEUR_SEUIL_RAG,
            "donnees": settings.ASSISTANT_ROUTEUR_SEUIL_DATA,
        },
        "fusion": {
            "active": settings.ASSISTANT_FUSION_ENABLED,
            "clarification": settings.ASSISTANT_CLARIFICATION,
            "seuil_documents": settings.seuil_rag_assistant,
            "top_k": settings.ASSISTANT_RAG_TOP_K,
        },
        "regle": (
            "Le chemin est déterminé par le code, jamais par un modèle de "
            "langage. Le modèle ne reçoit que des résultats déjà calculés."
        ),
    }