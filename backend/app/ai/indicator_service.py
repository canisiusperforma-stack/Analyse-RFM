"""Identification de l'indicateur, requête backend et calcul exact.

Ce module matérialise les étapes 3 à 6 du pipeline imposé :

    3. identification de l'indicateur   — `identifier`
    4. requête backend                  — `collecter`
    5. calcul exact                     — `calculer`
    6. résultat structuré               — `ResultatStructure`

Il est écrit **sans modèle de langage**, comme `query_analyzer`. C'est cette
séparation qui rend la règle fondamentale vérifiable plutôt que déclarative :
le modèle ne choisit ni la source, ni l'agrégat, ni la formule. Il reçoit à
l'étape 7 un résultat déjà calculé et n'a plus qu'à le dire en français.

Pourquoi le calcul est ici, et pas dans le modèle
    Une question comme « quel mois présente le montant remboursé le plus élevé »
    ou « compare les actifs et les pensionnés » appelle une comparaison, un
    écart, une part. Si le modèle effectuait ce travail, il choisirait un mois
    parmi douze et pourrait se tromper : le validateur rejetterait alors la
    réponse, ou pire, accepterait une erreur dont la valeur numérique
    proviendrait bien des données. Le calcul est donc fait ici, en Python, et
    le modèle se contente de le narrer. Le validateur contrôle ensuite que les
    chiffres cités sont bien parmi ceux que ce calcul a produits.

Absence de données
    Une étape de calcul qui ne peut pas aboutir ne renvoie pas un zéro. Elle
    renvoie un `ResultatStructure` marqué indisponible, avec le motif exact
    (exercice absent, source sans rattachement RFM, série vide). C'est ce qui
    permet à l'assistant de répondre « cette donnée n'est pas disponible »
    au lieu de laisser le modèle combler le vide.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional

from app.ai.query_analyzer import (
    AGREGATION_ARGMAX,
    AGREGATION_ARGMIN,
    AGREGATION_COMPARAISON,
    AGREGATION_TOTAL,
    IntentionQuery,
)
from app.services import (
    analyse_service,
    anomalie_service,
    budget_service,
    prevision_service,
)
from app.services import beneficiaires_service
from app.utils.logging import get_logger

logger = get_logger(__name__)

# --- Unités de restitution -------------------------------------------------

UNITE_MONTANT = "montant"
UNITE_EFFECTIF = "effectif"
UNITE_POURCENTAGE = "pourcentage"
UNITE_DUREE = "jours"
UNITE_TEXTE = "texte"

# --- Statut de disponibilité d'un résultat calculé -------------------------

DISPONIBLE = "disponible"
PARTIEL = "partiel"
ABSENT = "absent"

LIBELLES_MOIS = (
    "janvier", "février", "mars", "avril", "mai", "juin",
    "juillet", "août", "septembre", "octobre", "novembre", "décembre",
)


# --- Mise en forme des valeurs ---------------------------------------------

#: Formatage canonique d'une valeur, partagé par tous les rendus : la réponse
#: déterministe, le prompt destiné au modèle, et le champ `valeur_affichee`
#: des mesures. Ces trois rendus doivent convenir *exactement*, faute de quoi le
#: modèle recopierait une écriture que `response_validator` ne reconnaîtrait
#: pas, et l'utilisateur verrait un chiffre différent selon l'endroit où il le
#: lit. D'où une fonction unique, et non trois implémentations concordantes.
#:
#: Le formatage est une présentation : aucune valeur n'est recalculée, convertie
#: ni reformulée. L'arrondi éventuel est celui qu'un affichage dans une unité
#: lisible impose, et il est fait une fois pour tous les rendus.


def formater_valeur(valeur: Any, unite: str) -> str:
    """Rend une valeur dans son unité, sans jamais la recalculer."""
    if valeur is None:
        return "non disponible"
    if unite == UNITE_TEXTE:
        return str(valeur)
    if unite == UNITE_POURCENTAGE:
        return f"{float(valeur) * 100:.1f} %".replace(".", ",")
    if unite == UNITE_MONTANT:
        return f"{round(float(valeur)):,} Ar".replace(",", " ")
    if unite == UNITE_EFFECTIF:
        return f"{int(round(float(valeur))):,}".replace(",", " ")
    if unite == UNITE_DUREE:
        return f"{float(valeur):.1f} ans".replace(".", ",")
    return str(valeur)


def _normaliser(texte: str) -> str:
    """Minuscules, sans accents, ponctuation réduite à des espaces."""
    sans_accents = unicodedata.normalize("NFKD", (texte or "").lower())
    sans_accents = "".join(
        caractere
        for caractere in sans_accents
        if not unicodedata.combining(caractere)
    )
    return re.sub(r"[^a-z0-9]+", " ", sans_accents).strip()


# ---------------------------------------------------------------------------
# Étape 3 : définition et catalogue des indicateurs
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DefinitionIndicateur:
    """Fiche d'un indicateur : libellé, unité, source, calcul et motifs.

    `collecter` est l'unique fonction autorisée à interroger la base : elle
    renvoie des faits bruts. `calculer` transforme ces faits en mesures. Les
    deux restent séparées pour que la provenance de chaque valeur reste
    traçable — les faits viennent du backend, les mesures sont dérivées de ces
    faits par du code déterministe.
    """

    code: str
    libelle: str
    unite: str
    module: str
    permission: str
    fonction_requete: str
    collecter: Callable[[Optional[int]], Awaitable[Any]]
    calculer: Callable[[Any, IntentionQuery], Optional[dict[str, Any]]]
    motifs: tuple[str, ...]
    agregation: str = AGREGATION_TOTAL
    # Situations (actif / pensionne) auxquelles l'indicateur s'applique
    # spécifiquement. Sert à départager « combien de bénéficiaires sont
    # actifs » (population.actifs) de « combien de bénéficiaires » (population.total).
    situations: tuple[str, ...] = ()
    # Priorité départageant deux indicateurs à score égal. Les indicateurs
    # génériques d'un domaine (budget.credits sur « budget », population.total
    # sur « population ») restent à 0 : sur « quel est le solde du budget »,
    # « solde » doit l'emporter sur le mot de domaine « budget ».
    priorite: int = 1


@dataclass
class Mesure:
    """Valeur calculée, avec son libellé, son unité et sa précision d'affichage."""

    cle: str
    libelle: str
    valeur: Any
    unite: str
    precision: Optional[int] = None

    @property
    def numerique(self) -> Optional[float]:
        return _nombre(self.valeur)

    def to_dict(self) -> dict[str, Any]:
        return {
            "cle": self.cle,
            "libelle": self.libelle,
            "valeur": self.valeur,
            "unite": self.unite,
            "precision": self.precision,
            # Rendu prêt à afficher, produit par le formatage canonique.
            # L'interface s'affiche tel quel plutôt que de refaire le format en
            # JavaScript : la chaîne montrée à l'utilisateur est alors celle
            # que le contrôle numérique a confrontée à l'index des données,
            # et deux rendus ne peuvent pas diverger.
            "valeur_affichee": formater_valeur(self.valeur, self.unite),
        }


@dataclass
class ResultatStructure:
    """Étape 6 : résultat structuré, seule matière des chiffres cités."""

    indicateur: str
    libelle: str
    unite: str
    statut: str = DISPONIBLE
    agregation: str = AGREGATION_TOTAL
    mesures: list[Mesure] = field(default_factory=list)
    texte: Optional[str] = None
    tableau: Optional[dict[str, Any]] = None
    sources: list[dict[str, Any]] = field(default_factory=list)
    absence: Optional[str] = None
    note: Optional[str] = None

    @property
    def exploitable(self) -> bool:
        """Vrai si des chiffres peuvent être cités."""
        return self.statut != ABSENT and bool(self.mesures)

    @property
    def complet(self) -> bool:
        return self.statut == DISPONIBLE

    def mesure(self, cle: str) -> Optional[Mesure]:
        return next((item for item in self.mesures if item.cle == cle), None)

    def resume(self) -> dict[str, Any]:
        return {
            "indicateur": self.indicateur,
            "libelle": self.libelle,
            "unite": self.unite,
            "statut": self.statut,
            "agregation": self.agregation,
            "mesures": [mesure.to_dict() for mesure in self.mesures],
            "texte": self.texte,
            "tableau": self.tableau,
            "absence": self.absence,
            "note": self.note,
        }


def _nombre(valeur: Any) -> Optional[float]:
    """Convertit en flottant, ou renvoie None si la valeur n'est pas numérique."""
    if valeur is None or isinstance(valeur, bool):
        return None
    try:
        return float(valeur)
    except (TypeError, ValueError):
        return None


def _absent(indicateur: DefinitionIndicateur, motif: str, exercice: Any) -> ResultatStructure:
    """Construit un résultat marqué absent, avec le motif de l'absence."""
    logger.info("Indicateur %s indisponible : %s", indicateur.code, motif)
    return ResultatStructure(
        indicateur=indicateur.code,
        libelle=indicateur.libelle,
        unite=indicateur.unite,
        statut=ABSENT,
        absence=motif,
        sources=[
            {
                "module": indicateur.module,
                "fonction": indicateur.fonction_requete,
                "exercice": exercice,
                "libelle": indicateur.libelle,
            }
        ],
    )


def _libelle_mois(item: dict[str, Any]) -> str:
    """Libellé lisible d'un point de série (« mars »)."""
    libelle = item.get("libelle")
    if libelle:
        return str(libelle)
    mois = item.get("mois")
    if isinstance(mois, int) and 1 <= mois <= 12:
        return LIBELLES_MOIS[mois - 1]
    return "non précisé"


def _serie(faits: Any, *cles: str) -> list[dict[str, Any]]:
    """Première série mensuelle présente dans les faits, normalisée en liste."""
    if not isinstance(faits, dict):
        return []
    for cle in cles:
        serie = faits.get(cle)
        if isinstance(serie, list) and serie:
            return [item for item in serie if isinstance(item, dict)]
    return []


def _exercice_de(faits: Any) -> Optional[int]:
    if not isinstance(faits, dict):
        return None
    valeur = faits.get("exercice")
    return int(valeur) if valeur is not None else None


# ---------------------------------------------------------------------------
# Étape 5 : calculs — une fonction par indicateur
# ---------------------------------------------------------------------------


def _valeur_simple(faits: Any, chemin: tuple[str, ...]) -> Any:
    courant: Any = faits
    for cle in chemin:
        if not isinstance(courant, dict):
            return None
        courant = courant.get(cle)
    return courant


def _calcul_budget_champ(faits: Any, intention: IntentionQuery) -> Optional[dict[str, Any]]:
    """Rend un champ du bloc `total` de la synthèse budgétaire."""
    champ = intention.indicateur_cle
    definition = CHAMPS_BUDGET.get(champ)
    if definition is None:
        return None
    libelle, unite = definition
    valeur = _valeur_simple(faits, ("total", champ))
    if _nombre(valeur) is None:
        return None
    precision = 4 if unite == UNITE_POURCENTAGE else None
    return {
        "mesures": [
            Mesure(
                cle=champ,
                libelle=libelle,
                valeur=valeur,
                unite=unite,
                precision=precision,
            )
        ],
        "note": f"valeur lue dans la synthèse budgétaire (exercice {_exercice_de(faits)})",
    }


def _calcul_budget_extremum(faits: Any, intention: IntentionQuery) -> Optional[dict[str, Any]]:
    """Mois de plus forte ou de plus faible exécution, calculé par le backend.

    C'est ici que « quel mois est le plus élevé ? » est résolu. Le modèle se
    contente d'énoncer le mois et la valeur déjà retenus.
    """
    champ = intention.indicateur_cle or "paiement"
    libelle_champ, unite = CHAMPS_SERIE_BUDGET.get(champ, (champ, UNITE_MONTANT))
    serie = _serie(faits, "serie_mensuelle", "execution_mensuelle")
    retenus = [item for item in serie if _nombre(item.get(champ)) is not None]
    if not retenus:
        return None

    if intention.agregation == AGREGATION_ARGMIN:
        retenu = min(retenus, key=lambda item: float(item[champ]))
        mention = f"mois de plus faible {libelle_champ}"
    else:
        retenu = max(retenus, key=lambda item: float(item[champ]))
        mention = f"mois de plus forte {libelle_champ}"

    return {
        "mesures": [
            Mesure(
                cle=champ,
                libelle=libelle_champ,
                valeur=retenu.get(champ),
                unite=unite,
            ),
            Mesure(
                cle="mois",
                libelle=mention,
                valeur=_libelle_mois(retenu),
                unite=UNITE_TEXTE,
            ),
        ],
        "note": "extrémum calculé par le backend sur la série mensuelle d'exécution",
    }


def _calcul_population_effectif(faits: Any, intention: IntentionQuery) -> Optional[dict[str, Any]]:
    """Effectif d'une catégorie de population (total, actifs, pensionnés, RFM)."""
    champ = intention.indicateur_cle or "total"
    definition = CHAMPS_POPULATION.get(champ)
    if definition is None:
        return None
    libelle, unite = definition
    valeur = _valeur_simple(faits, (champ,))
    if _nombre(valeur) is None:
        return None
    return {
        "mesures": [
            Mesure(cle=champ, libelle=libelle, valeur=valeur, unite=unite)
        ],
        "note": f"statistique de population (source {faits.get('source', 'inconnue')})",
    }


def _calcul_population_croisement(faits: Any, intention: IntentionQuery) -> Optional[dict[str, Any]]:
    """Croisement situation × statut RFM.

    Répond à « combien de pensionnés ont bénéficié du RFM ? ». La situation
    demandée est portée par l'analyse ; le comptage provient du backend et n'est
    que restitué ici.
    """
    if not isinstance(faits, dict) or not faits.get("disponible"):
        return None

    situation = _situation_demandee(intention)
    lignes = [ligne for ligne in (faits.get("croisement") or []) if isinstance(ligne, dict)]
    if not lignes:
        return None

    if situation is None:
        # Aucun filtre de situation : total de la population ayant bénéficié du RFM.
        retenues = lignes
        intitule = "bénéficiaires ayant bénéficié du RFM"
    else:
        ligne = next(
            (item for item in lignes if str(item.get("situation")) == situation), None
        )
        if ligne is None:
            return None
        retenues = [ligne]
        intitule = (
            f"bénéficiaires ayant bénéficié du RFM — {ligne.get('situation_libelle', situation)}"
        )

    rfm = sum(int(ligne.get("rfm") or 0) for ligne in retenues)
    population = sum(int(ligne.get("total") or 0) for ligne in retenues)
    if not population:
        return None

    mesures = [
        Mesure(cle="rfm", libelle=intitule, valeur=rfm, unite=UNITE_EFFECTIF),
        Mesure(
            cle="population",
            libelle="effectif de la population considérée",
            valeur=population,
            unite=UNITE_EFFECTIF,
        ),
        Mesure(
            cle="part",
            libelle="part ayant bénéficié du RFM",
            valeur=round(rfm / population, 4),
            unite=UNITE_POURCENTAGE,
            precision=4,
        ),
    ]
    return {
        "mesures": mesures,
        "tableau": {
            "colonnes": ["Situation", "Avec RFM", "Sans RFM", "Total"],
            "lignes": [
                [
                    ligne.get("situation_libelle") or ligne.get("situation"),
                    ligne.get("rfm"),
                    ligne.get("non_rfm"),
                    ligne.get("total"),
                ]
                for ligne in lignes
            ],
        },
        "note": "croisement calculé par le backend (situation × statut RFM)",
    }


def _calcul_population_comparaison(faits: Any, intention: IntentionQuery) -> Optional[dict[str, Any]]:
    """Écart et parts entre actifs et pensionnés.

    Répond à « compare les actifs et les pensionnés ». Le sens de lecture et les
    parts sont calculés ici, en Python ; le modèle les énonce.
    """
    actifs = _nombre(_valeur_simple(faits, ("actifs",)))
    pensionnes = _nombre(_valeur_simple(faits, ("pensionnes",)))
    if actifs is None or pensionnes is None or (actifs + pensionnes) == 0:
        return None

    total = actifs + pensionnes
    dominant = "actifs" if actifs > pensionnes else "pensionnés"
    mesures = [
        Mesure(cle="actifs", libelle="actifs", valeur=int(actifs), unite=UNITE_EFFECTIF),
        Mesure(cle="pensionnes", libelle="pensionnés", valeur=int(pensionnes), unite=UNITE_EFFECTIF),
        Mesure(
            cle="ecart",
            libelle="écart d'effectif",
            valeur=int(abs(actifs - pensionnes)),
            unite=UNITE_EFFECTIF,
        ),
        Mesure(
            cle="part_actifs",
            libelle="part des actifs",
            valeur=round(actifs / total, 4),
            unite=UNITE_POURCENTAGE,
            precision=4,
        ),
        Mesure(
            cle="part_pensionnes",
            libelle="part des pensionnés",
            valeur=round(pensionnes / total, 4),
            unite=UNITE_POURCENTAGE,
            precision=4,
        ),
    ]
    return {
        "mesures": mesures,
        "texte": f"catégorie majoritaire : {dominant}",
        "note": "comparaison calculée par le backend (écart et parts)",
    }


def _calcul_remboursement_extremum(faits: Any, intention: IntentionQuery) -> Optional[dict[str, Any]]:
    """Mois de plus fort ou de plus faible remboursement, calculé par le backend."""
    champ = intention.indicateur_cle or "montant_paye"
    libelle_champ, unite = CHAMPS_SERIE_REMBOURSEMENT.get(champ, (champ, UNITE_MONTANT))
    serie = _serie(faits, "evolution", "serie_mensuelle")
    retenus = [item for item in serie if _nombre(item.get(champ)) is not None]
    if not retenus:
        return None

    if intention.agregation == AGREGATION_ARGMIN:
        retenu = min(retenus, key=lambda item: float(item[champ]))
        mention = f"mois de plus faible {libelle_champ}"
    else:
        retenu = max(retenus, key=lambda item: float(item[champ]))
        mention = f"mois de plus forte {libelle_champ}"

    return {
        "mesures": [
            Mesure(
                cle=champ,
                libelle=libelle_champ,
                valeur=retenu.get(champ),
                unite=unite,
            ),
            Mesure(
                cle="mois",
                libelle=mention,
                valeur=_libelle_mois(retenu),
                unite=UNITE_TEXTE,
            ),
        ],
        "note": "extrémum calculé par le backend sur la série des remboursements",
    }


def _calcul_remboursement_synthese(faits: Any, intention: IntentionQuery) -> Optional[dict[str, Any]]:
    """Indicateur global des remboursements (demandes, paiements, taux)."""
    champ = intention.indicateur_cle or "demandes"
    definition = CHAMPS_REMBOURSEMENT.get(champ)
    if definition is None:
        return None
    libelle, unite = definition
    synthese = faits.get("synthese") if isinstance(faits, dict) else None
    valeur = _valeur_simple(synthese or {}, (champ,))
    if _nombre(valeur) is None:
        return None
    return {
        "mesures": [
            Mesure(
                cle=champ,
                libelle=libelle,
                valeur=valeur,
                unite=unite,
                precision=4 if unite == UNITE_POURCENTAGE else None,
            )
        ],
        "note": f"bilan de l'exercice {_exercice_de(faits)}",
    }


def _calcul_statistiques(faits: Any, intention: IntentionQuery) -> Optional[dict[str, Any]]:
    """Statistiques descriptives d'une variable numérique."""
    variable = intention.indicateur_cle or "montant_demande"
    descriptives = _valeur_simple(faits, ("descriptives", variable))
    if not isinstance(descriptives, dict) or not descriptives.get("nombre"):
        return None
    mesures = [
        Mesure(
            cle=f"{variable}_{statistique}",
            libelle=statistique,
            valeur=descriptives.get(statistique),
            unite=UNITE_DUREE if variable == "delai_jours" else UNITE_MONTANT,
        )
        for statistique in ("moyenne", "mediane", "ecart_type", "minimum", "maximum")
        if descriptives.get(statistique) is not None
    ]
    if not mesures:
        return None
    return {
        "mesures": mesures,
        "tableau": {
            "colonnes": ["Statistique", "Valeur"],
            "lignes": [[mesure.libelle, mesure.valeur] for mesure in mesures],
        },
        "note": "statistiques descriptives calculées par le backend",
    }


def _calcul_anomalies(faits: Any, intention: IntentionQuery) -> Optional[dict[str, Any]]:
    """Nombre d'anomalies détectées sur la période demandée."""
    total = _nombre(_valeur_simple(faits, ("total",)))
    if total is None:
        return None
    mesures = [
        Mesure(cle="total", libelle="anomalies détectées", valeur=int(total), unite=UNITE_EFFECTIF)
    ]
    comptes = faits.get("comptes") if isinstance(faits, dict) else None
    if isinstance(comptes, dict):
        mesures.extend(
            Mesure(
                cle=f"compte_{cle}",
                libelle=f"observations de niveau {cle}",
                valeur=int(valeur),
                unite=UNITE_EFFECTIF,
            )
            for cle, valeur in comptes.items()
            if _nombre(valeur) is not None
        )
    return {
        "mesures": mesures,
        "note": "détection établie par le backend (anomalie_service)",
    }


def _calcul_prevision(faits: Any, intention: IntentionQuery) -> Optional[dict[str, Any]]:
    """Projections de consommation produites par le modèle de prévision."""
    if not isinstance(faits, dict) or not faits:
        return None
    serie = faits.get("serie_mensuelle")
    if not isinstance(serie, list) or not serie:
        return None
    mesures = [
        Mesure(
            cle=f"prevision_{index}",
            libelle=str(item.get("mois") or item.get("periode") or f"période {index + 1}"),
            valeur=item.get("valeur", item.get("montant")),
            unite=UNITE_MONTANT,
        )
        for index, item in enumerate(serie[:6])
        if isinstance(item, dict)
    ]
    mesures = [mesure for mesure in mesures if _nombre(mesure.valeur) is not None]
    if not mesures:
        return None
    return {
        "mesures": mesures,
        "tableau": {
            "colonnes": ["Période", "Prévision"],
            "lignes": [[mesure.libelle, mesure.valeur] for mesure in mesures],
        },
        "note": "projection statistique du backend, non un engagement de dépense",
    }


def _situation_demandee(intention: IntentionQuery) -> Optional[str]:
    """Situation (actif / pensionne) explicitement demandée par l'utilisateur."""
    for situation in intention.situations:
        if situation in ("actif", "pensionne"):
            return situation
    return None


# ---------------------------------------------------------------------------
# Étape 4 : fonctions de collecte — seules lectures de la base autorisées
# ---------------------------------------------------------------------------


async def _collecter_budget(exercice: Optional[int]) -> Any:
    return await budget_service.calculer_synthese(exercice)


async def _collecter_population(exercice: Optional[int]) -> Any:
    return await beneficiaires_service.statistiques_population(exercice)


async def _collecter_croisement(exercice: Optional[int]) -> Any:
    return await beneficiaires_service.croisement_situation_rfm(exercice)


async def _collecter_remboursements(exercice: Optional[int]) -> Any:
    return await analyse_service.analyse_temporelle(exercice)


async def _collecter_statistiques(exercice: Optional[int]) -> Any:
    return await analyse_service.statistiques_data_science(exercice)


async def _collecter_anomalies(exercice: Optional[int]) -> Any:
    return await anomalie_service.lister_anomalies(exercice=exercice, limite=15)


async def _collecter_prevision(_exercice: Optional[int]) -> Any:
    return await prevision_service.generer_prevision()


# ---------------------------------------------------------------------------
# Catalogue
# ---------------------------------------------------------------------------

CHAMPS_BUDGET: dict[str, tuple[str, str]] = {
    "credits": ("crédits ouverts", UNITE_MONTANT),
    "lfi": ("crédits LFI", UNITE_MONTANT),
    "lfr": ("crédits LFR", UNITE_MONTANT),
    "engagement": ("montants engagés", UNITE_MONTANT),
    "liquidation": ("montants liquidés", UNITE_MONTANT),
    "ordonnancement": ("montants ordonnancés", UNITE_MONTANT),
    "execute": ("montants exécutés", UNITE_MONTANT),
    "disponible": ("crédits disponibles", UNITE_MONTANT),
    "solde": ("solde budgétaire", UNITE_MONTANT),
    "taux_execution": ("taux d'exécution", UNITE_POURCENTAGE),
    "lignes_budgetaires": ("lignes budgétaires", UNITE_EFFECTIF),
}

CHAMPS_SERIE_BUDGET: dict[str, tuple[str, str]] = {
    "engagement": ("engagements", UNITE_MONTANT),
    "liquidation": ("liquidations", UNITE_MONTANT),
    "ordonnancement": ("ordonnancements", UNITE_MONTANT),
    "paiement": ("paiements", UNITE_MONTANT),
    "cumul": ("cumul des paiements", UNITE_MONTANT),
}

CHAMPS_POPULATION: dict[str, tuple[str, str]] = {
    "total": ("bénéficiaires recensés", UNITE_EFFECTIF),
    "actifs": ("actifs", UNITE_EFFECTIF),
    "pensionnes": ("pensionnés", UNITE_EFFECTIF),
    "indetermines": ("bénéficiaires de situation indéterminée", UNITE_EFFECTIF),
    "beneficiaires_rfm": ("bénéficiaires ayant bénéficié du RFM", UNITE_EFFECTIF),
    "moyenne_age": ("âge moyen", UNITE_DUREE),
    "age_minimal": ("âge minimal", UNITE_DUREE),
    "age_maximal": ("âge maximal", UNITE_DUREE),
}

CHAMPS_REMBOURSEMENT: dict[str, tuple[str, str]] = {
    "demandes": ("demandes de remboursement", UNITE_EFFECTIF),
    "payes": ("dossiers payés", UNITE_EFFECTIF),
    "montant_demande": ("montant demandé", UNITE_MONTANT),
    "montant_paye": ("montant remboursé", UNITE_MONTANT),
    "taux_execution": ("taux d'exécution des remboursements", UNITE_POURCENTAGE),
    "moyenne": ("montant moyen demandé", UNITE_MONTANT),
    "moyenne_paye": ("montant moyen remboursé", UNITE_MONTANT),
}

CHAMPS_SERIE_REMBOURSEMENT: dict[str, tuple[str, str]] = {
    "montant_paye": ("montant remboursé", UNITE_MONTANT),
    "montant_demande": ("montant demandé", UNITE_MONTANT),
    "demandes": ("nombre de demandes", UNITE_EFFECTIF),
    "payes": ("nombre de dossiers payés", UNITE_EFFECTIF),
}

INDICATEURS: tuple[DefinitionIndicateur, ...] = (
    # --- Budget -----------------------------------------------------------
    DefinitionIndicateur(
        code="budget.taux_execution",
        libelle="Taux d'exécution budgétaire",
        unite=UNITE_POURCENTAGE,
        module="budget",
        permission="budget:voir",
        fonction_requete="budget_service.calculer_synthese",
        collecter=_collecter_budget,
        calculer=_calcul_budget_champ,
        motifs=(
            r"taux d execution",
            r"taux d execution",
            r"pourcentage d execution",
            r"taux d execution du budget",
            r"taux de realisation",
        ),
    ),
    DefinitionIndicateur(
        code="budget.credits",
        libelle="Crédits ouverts",
        unite=UNITE_MONTANT,
        module="budget",
        permission="budget:voir",
        fonction_requete="budget_service.calculer_synthese",
        collecter=_collecter_budget,
        calculer=_calcul_budget_champ,
        motifs=(
            r"credits ouverts",
            r"credits votes",
            r"budget vote",
            r"montant du budget",
            r"combien de credits",
            r"credits disponibles",
            r"credits",
            r"budget",
        ),
        priorite=0,
    ),
    DefinitionIndicateur(
        code="budget.execute",
        libelle="Montants exécutés",
        unite=UNITE_MONTANT,
        module="budget",
        permission="budget:voir",
        fonction_requete="budget_service.calculer_synthese",
        collecter=_collecter_budget,
        calculer=_calcul_budget_champ,
        motifs=(
            r"montants executes",
            r"montant execute",
            r"depenses engagees",
            r"depenses reelles",
            r"execute",
        ),
    ),
    DefinitionIndicateur(
        code="budget.disponible",
        libelle="Crédits disponibles",
        unite=UNITE_MONTANT,
        module="budget",
        permission="budget:voir",
        fonction_requete="budget_service.calculer_synthese",
        collecter=_collecter_budget,
        calculer=_calcul_budget_champ,
        motifs=(r"credits disponibles", r"reste disponible", r"disponible", r"encours"),
    ),
    DefinitionIndicateur(
        code="budget.solde",
        libelle="Solde budgétaire",
        unite=UNITE_MONTANT,
        module="budget",
        permission="budget:voir",
        fonction_requete="budget_service.calculer_synthese",
        collecter=_collecter_budget,
        calculer=_calcul_budget_champ,
        motifs=(r"solde", r"decouvert", r"deficit"),
    ),
    DefinitionIndicateur(
        code="budget.engagement",
        libelle="Montants engagés",
        unite=UNITE_MONTANT,
        module="budget",
        permission="budget:voir",
        fonction_requete="budget_service.calculer_synthese",
        collecter=_collecter_budget,
        calculer=_calcul_budget_champ,
        motifs=(r"montants engages", r"engagements", r"engage"),
    ),
    DefinitionIndicateur(
        code="budget.mois_extremum",
        libelle="Mois d'exécution extreme",
        unite=UNITE_MONTANT,
        module="budget",
        permission="budget:voir",
        fonction_requete="budget_service.calculer_synthese",
        collecter=_collecter_budget,
        calculer=_calcul_budget_extremum,
        motifs=(
            r"mois.*(eleve|grand|gros|haut|fort|bas|petit|faible|maximum|minimum)",
            r"quel mois",
        ),
        agregation=AGREGATION_ARGMAX,
    ),
    # --- Population -------------------------------------------------------
    DefinitionIndicateur(
        code="population.croisement",
        libelle="Croisement situation et statut RFM",
        unite=UNITE_EFFECTIF,
        module="beneficiaires",
        permission="beneficiaires:voir",
        fonction_requete="beneficiaires_service.croisement_situation_rfm",
        collecter=_collecter_croisement,
        calculer=_calcul_population_croisement,
        motifs=(
            r"(?:actifs?|pensionnes?).*(?:beneficie|bénéficie|touche|concerne|adhere).*rfm",
            r"(?:beneficie|bénéficie|touche|concerne|adhere).*rfm.*(?:actifs?|pensionnes?)",
            r"rfm.*(?:actifs?|pensionnes?)",
            r"combien de (?:actifs?|pensionnes?)",
        ),
        situations=("actif", "pensionne"),
    ),
    DefinitionIndicateur(
        code="population.comparaison_situations",
        libelle="Comparaison des situations",
        unite=UNITE_EFFECTIF,
        module="beneficiaires",
        permission="beneficiaires:voir",
        fonction_requete="beneficiaires_service.statistiques_population",
        collecter=_collecter_population,
        calculer=_calcul_population_comparaison,
        motifs=(
            r"compare\w* (?:le |la |les |nombre de |d )*actifs?\w* (?:et|aux?|avec) (?:les |la |de |d )*pensionnes?\w*",
            r"comparaison (?:des |de )?actifs?\w* (?:et|aux?) (?:les |la |de )*pensionnes?\w*",
            r"actifs?\w* (?:et|aux?|avec) (?:les |la |de )*pensionnes?\w*",
            r"pensionnes?\w* (?:et|aux?|avec) (?:les |la |de )*actifs?\w*",
        ),
        agregation=AGREGATION_COMPARAISON,
    ),
    DefinitionIndicateur(
        code="population.actifs",
        libelle="Actifs",
        unite=UNITE_EFFECTIF,
        module="beneficiaires",
        permission="beneficiaires:voir",
        fonction_requete="beneficiaires_service.statistiques_population",
        collecter=_collecter_population,
        calculer=_calcul_population_effectif,
        motifs=(r"nombre d actifs", r"combien d actifs", r"actifs", r"salaries"),
        situations=("actif",),
    ),
    DefinitionIndicateur(
        code="population.pensionnes",
        libelle="Pensionnés",
        unite=UNITE_EFFECTIF,
        module="beneficiaires",
        permission="beneficiaires:voir",
        fonction_requete="beneficiaires_service.statistiques_population",
        collecter=_collecter_population,
        calculer=_calcul_population_effectif,
        motifs=(r"nombre de pensionnes", r"combien de pensionnes", r"pensionnes", r"retraites"),
        situations=("pensionne",),
    ),
    DefinitionIndicateur(
        code="population.beneficiaires_rfm",
        libelle="Bénéficiaires ayant bénéficié du RFM",
        unite=UNITE_EFFECTIF,
        module="beneficiaires",
        permission="beneficiaires:voir",
        fonction_requete="beneficiaires_service.statistiques_population",
        collecter=_collecter_population,
        calculer=_calcul_population_effectif,
        motifs=(
            r"beneficiaires rfm",
            r"beneficiaires du rfm",
            r"ont beneficie du rfm",
            r"beneficie du rfm",
            r"beneficie\w* le rfm",
            r"touch\w* (?:le |du |par le )?rfm",
            r"population rfm",
            r"adher\w* au rfm",
        ),
    ),
    DefinitionIndicateur(
        code="population.total",
        libelle="Population recensée",
        unite=UNITE_EFFECTIF,
        module="beneficiaires",
        permission="beneficiaires:voir",
        fonction_requete="beneficiaires_service.statistiques_population",
        collecter=_collecter_population,
        calculer=_calcul_population_effectif,
        motifs=(
            r"combien de beneficiaires",
            r"nombre de beneficiaires",
            r"nombre de beneficiaire",
            r"population",
            r"effectif",
            r"recenses",
            r"beneficiaires",
        ),
        priorite=0,
    ),
    DefinitionIndicateur(
        code="population.moyenne_age",
        libelle="Âge moyen",
        unite=UNITE_DUREE,
        module="beneficiaires",
        permission="beneficiaires:voir",
        fonction_requete="beneficiaires_service.statistiques_population",
        collecter=_collecter_population,
        calculer=_calcul_population_effectif,
        motifs=(r"age moyen", r"moyenne d age", r" ages? moyen"),
    ),
    # --- Remboursements ---------------------------------------------------
    DefinitionIndicateur(
        code="remboursements.mois_extremum",
        libelle="Mois de remboursement extreme",
        unite=UNITE_MONTANT,
        module="analyses",
        permission="analyses:voir",
        fonction_requete="analyse_service.analyse_temporelle",
        collecter=_collecter_remboursements,
        calculer=_calcul_remboursement_extremum,
        motifs=(
            r"mois.*(?:rembours\w*|montant).*(?:eleve|grand|gros|haut|fort|bas|petit|faible|maximum|minimum|max|min)",
            r"quel mois.*rembours",
            r"mois le plus",
            r"mois du plus",
        ),
        agregation=AGREGATION_ARGMAX,
    ),
    DefinitionIndicateur(
        code="remboursements.montant_paye",
        libelle="Montant remboursé",
        unite=UNITE_MONTANT,
        module="analyses",
        permission="analyses:voir",
        fonction_requete="analyse_service.analyse_temporelle",
        collecter=_collecter_remboursements,
        calculer=_calcul_remboursement_synthese,
        motifs=(
            r"montant rembourse",
            r"montants rembourses",
            r"total rembourse",
            r"remboursements? (?:effectue|verse|total)",
            r"combien (?:a|ont) ete rembourse",
        ),
    ),
    DefinitionIndicateur(
        code="remboursements.demandes",
        libelle="Demandes de remboursement",
        unite=UNITE_EFFECTIF,
        module="analyses",
        permission="analyses:voir",
        fonction_requete="analyse_service.analyse_temporelle",
        collecter=_collecter_remboursements,
        calculer=_calcul_remboursement_synthese,
        motifs=(
            r"nombre de demandes",
            r"combien de demandes",
            r"nombre de dossiers",
            r"combien de dossiers",
            r"demandes? de remboursement",
        ),
    ),
    DefinitionIndicateur(
        code="remboursements.taux_execution",
        libelle="Taux d'exécution des remboursements",
        unite=UNITE_POURCENTAGE,
        module="analyses",
        permission="analyses:voir",
        fonction_requete="analyse_service.analyse_temporelle",
        collecter=_collecter_remboursements,
        calculer=_calcul_remboursement_synthese,
        motifs=(
            r"taux d execution des remboursements",
            r"taux de remboursement",
            r"taux d execution",
        ),
    ),
    # --- Analyses, anomalies, prévisions -----------------------------------
    DefinitionIndicateur(
        code="analyses.statistiques",
        libelle="Statistiques descriptives",
        unite=UNITE_MONTANT,
        module="analyses",
        permission="analyses:voir",
        fonction_requete="analyse_service.statistiques_data_science",
        collecter=_collecter_statistiques,
        calculer=_calcul_statistiques,
        motifs=(
            r"statistiques? (?:descriptive|descriptives)",
            r"statistiques?",
            r"mediane",
            r"ecart type",
            r"quartiles?",
            r"distributio?n?",
        ),
    ),
    DefinitionIndicateur(
        code="anomalies.total",
        libelle="Anomalies détectées",
        unite=UNITE_EFFECTIF,
        module="anomalies",
        permission="anomalies:voir",
        fonction_requete="anomalie_service.lister_anomalies",
        collecter=_collecter_anomalies,
        calculer=_calcul_anomalies,
        motifs=(r"anomalies?", r"irrregularite", r"cas suspects", r"alertes?"),
    ),
    DefinitionIndicateur(
        code="previsions.serie",
        libelle="Prévision de consommation",
        unite=UNITE_MONTANT,
        module="previsions",
        permission="previsions:voir",
        fonction_requete="prevision_service.generer_prevision",
        collecter=_collecter_prevision,
        calculer=_calcul_prevision,
        motifs=(r"previsions?", r"prevoir", r"projections?", r"mois a venir"),
    ),
)

INDICATEURS_PAR_CODE: dict[str, DefinitionIndicateur] = {
    indicateur.code: indicateur for indicateur in INDICATEURS
}

# Le champ à calculer est déduit de l'indicateur et de la question ; il est
# porté par l'intention pour que les fonctions de calcul restent pures.
CHAMPS_PAR_CODE: dict[str, tuple[str, ...]] = {
    "budget.taux_execution": ("taux_execution",),
    "budget.credits": ("credits",),
    "budget.execute": ("execute",),
    "budget.disponible": ("disponible",),
    "budget.solde": ("solde",),
    "budget.engagement": ("engagement",),
    "budget.mois_extremum": ("paiement", "cumul", "engagement", "liquidation", "ordonnancement"),
    "population.actifs": ("actifs",),
    "population.pensionnes": ("pensionnes",),
    "population.beneficiaires_rfm": ("beneficiaires_rfm",),
    "population.total": ("total",),
    "population.moyenne_age": ("moyenne_age",),
    "remboursements.montant_paye": ("montant_paye",),
    "remboursements.demandes": ("demandes",),
    "remboursements.taux_execution": ("taux_execution",),
    "remboursements.mois_extremum": ("montant_paye", "montant_demande", "demandes", "payes"),
    "analyses.statistiques": ("montant_demande", "montant_paye", "delai_jours"),
    "population.croisement": (),
    "population.comparaison_situations": (),
    "anomalies.total": (),
    "previsions.serie": (),
}

MOTIFS_PAR_CODE: dict[str, tuple[re.Pattern[str], ...]] = {
    indicateur.code: tuple(
        re.compile(r"\b(?:" + motif + r")\b", re.IGNORECASE)
        for motif in indicateur.motifs
    )
    for indicateur in INDICATEURS
}


# ---------------------------------------------------------------------------
# Étape 3 : identification
# ---------------------------------------------------------------------------


JETONS_NEUFS = frozenset(
    {
        "de", "du", "des", "le", "la", "les", "un", "une", "et", "ou", "en",
        "pour", "par", "sur", "dans", "avec", "au", "aux", "ce", "cette", "ces",
        "que", "qui", "quoi", "est", "sont", "ont", "a", "ont", "ne", "nous",
        "je", "mon", "ma", "mes", "nos", "notre", "quel", "quelle", "quels",
        "quelles", "quelque", "y", "plus", "moins", "tres", "the", "est",
        "ceci", "cela", "ca", "nombre", "combien", "quel", "quels",
    }
)

BONUS_SITUATION = 3
# Le bonus ne vaut que si la question nomme une seule situation. « Combien de
# bénéficiaires sont actifs » cible les actifs, mais « compare les actifs et
# les pensionnés » les nomme tous les deux : c'est une comparaison, et aucun
# indicateur de situation ne doit alors être privilégié.


def _poids_correspondance(correspondances: list[str]) -> int:
    """Pondère une correspondance par les mots pleins qu'elle apporte.

    Compter les occurrences ne suffit pas à départager deux indicateurs qui
    tombent à égalité sur une question courte, et sommer les correspondances
    compterait deux fois le même mot : sur « combien de bénéficiaires ont
    touché le RFM », les motifs « combien de bénéficiaires » et « bénéficiaires »
    se recouvrent, et `population.total` l'emporterait à tort.

    On compte donc l'union des mots pleins réellement couverts :
    « combien de bénéficiaires ont bénéficié du RFM » couvre quatre mots pour le
    croisement (pensionnés, ont, bénéficié, RFM) contre trois pour le simple
    compteur de bénéficiaires RFM, et le premier l'emporte à juste titre.
    """
    mots: set[str] = set()
    for correspondance in correspondances:
        for mot in _normaliser(correspondance).split():
            if len(mot) >= 2 and mot not in JETONS_NEUFS:
                mots.add(mot)
    return len(mots)


def _score_indicateur(question_norm: str, intention: IntentionQuery) -> dict[str, int]:
    """Score chaque indicateur : mots pleins couverts, plus bonus de situation."""
    scores: dict[str, int] = {}
    for code, motifs in MOTIFS_PAR_CODE.items():
        correspondances: list[str] = []
        for motif in motifs:
            correspondances.extend(motif.findall(question_norm))
        if not correspondances:
            continue
        score = _poids_correspondance(correspondances)
        situations = INDICATEURS_PAR_CODE[code].situations
        if (
            situations
            and len(intention.situations) == 1
            and any(
                situation in intention.situations for situation in situations
            )
        ):
            score += BONUS_SITUATION
        scores[code] = score
    return scores


def _resoudre_champ(code: str, question_norm: str) -> Optional[str]:
    """Champ précis demandé par la question, si elle en nomme un."""
    candidats = CHAMPS_PAR_CODE.get(code, ())
    for champ in candidats:
        libelle, _ = (
            CHAMPS_BUDGET.get(champ)
            or CHAMPS_POPULATION.get(champ)
            or CHAMPS_REMBOURSEMENT.get(champ)
            or CHAMPS_SERIE_BUDGET.get(champ)
            or CHAMPS_SERIE_REMBOURSEMENT.get(champ)
            or (None, None)
        )
        if not libelle:
            continue
        if _normaliser(libelle) in question_norm:
            return champ
    return candidats[0] if candidats else None


def identifier(intention: IntentionQuery) -> Optional[DefinitionIndicateur]:
    """Étape 3 : associe à la question l'indicateur dont le backend va calculer la valeur.

    Le choix est fait par correspondance de motifs, jamais par le modèle. Le
    score compte les mots pleins couverts, et les indicateurs liés à une
    situation explicitement demandée sont poussés en avant : « combien de
    bénéficiaires sont actifs » vise `population.actifs` et non le total.
    """
    question_norm = _normaliser(intention.question)
    if not question_norm:
        return None

    scores = _score_indicateur(question_norm, intention)
    if not scores:
        return None

    meilleur_code = max(
        scores,
        key=lambda code: (
            scores[code],
            INDICATEURS_PAR_CODE[code].priorite,
            len(INDICATEURS_PAR_CODE[code].motifs),
        ),
    )
    return INDICATEURS_PAR_CODE[meilleur_code]


# ---------------------------------------------------------------------------
# Étapes 4 et 5
# ---------------------------------------------------------------------------


async def resoudre(
    intention: IntentionQuery,
    exercice: Optional[int] = None,
) -> tuple[ResultatStructure, Any]:
    """Enchaîne les étapes 3 à 6 et renvoie (résultat structuré, faits bruts)."""
    indicateur = identifier(intention)
    if indicateur is None:
        return (
            ResultatStructure(
                indicateur="aucun",
                libelle="Aucun indicateur identifié",
                unite=UNITE_TEXTE,
                statut=ABSENT,
                absence=(
                    "Aucun indicateur de la plateforme ne correspond à cette question."
                ),
            ),
            None,
        )

    intention.indicateur_cle = _resoudre_champ(indicateur.code, _normaliser(intention.question))
    if intention.agregation == AGREGATION_TOTAL and indicateur.agregation != AGREGATION_TOTAL:
        intention.agregation = indicateur.agregation

    source = {
        "module": indicateur.module,
        "fonction": indicateur.fonction_requete,
        "exercice": exercice,
        "libelle": indicateur.libelle,
    }

    try:
        faits = await indicateur.collecter(exercice)
    except Exception as erreur:  # noqa: BLE001
        logger.warning("Collecte impossible pour %s : %s", indicateur.code, erreur)
        return (
            _absent(
                indicateur,
                "La requête au backend n'a pas abouti pour cet indicateur.",
                exercice,
            ),
            None,
        )

    if not faits:
        return (
            _absent(
                indicateur,
                "Aucune donnée n'est enregistrée en base pour cet indicateur.",
                exercice,
            ),
            None,
        )

    # Le croisement RFM porte son propre motif d'indisponibilité : une source
    # reconstituée par importation ne permet pas de déduire le statut RFM.
    if isinstance(faits, dict) and faits.get("disponible") is False:
        return (
            _absent(indicateur, faits.get("motif") or "Donnée indisponible.", exercice),
            faits,
        )

    mesure = indicateur.calculer(faits, intention)
    if not mesure or not mesure.get("mesures"):
        return (
            _absent(
                indicateur,
                "Les données nécessaires au calcul de cet indicateur ne sont pas "
                "disponibles pour l'exercice demandé.",
                exercice,
            ),
            faits,
        )

    resultat = ResultatStructure(
        indicateur=indicateur.code,
        libelle=indicateur.libelle,
        unite=indicateur.unite,
        statut=DISPONIBLE,
        agregation=intention.agregation,
        mesures=mesure["mesures"],
        texte=mesure.get("texte"),
        tableau=mesure.get("tableau"),
        note=mesure.get("note"),
        sources=[{**source, "exercice": _exercice_de(faits) or exercice}],
    )
    return resultat, faits


def referentiel_indicateurs() -> list[dict[str, Any]]:
    """Catalogue exposé par l'API : ce que l'assistant sait réellement calculer."""
    return [
        {
            "code": indicateur.code,
            "libelle": indicateur.libelle,
            "unite": indicateur.unite,
            "module": indicateur.module,
            "agregation": indicateur.agregation,
        }
        for indicateur in INDICATEURS
    ]
