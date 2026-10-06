"""Cibles de déversement des lignes importées vers les collections métier.

L'import conserve par défaut les données dans les collections de staging
(`importations_*`). Ces collections ne sont lues que par le service des
bénéficiaires, en repli. `budgets_rfm`, `executions` et `remboursements` n'ont
aucun repli : sans déversement, leurs exercices restent invisibles.

Chaque cible déclare :

- le titre de feuille accepté (normalisé) ;
- la collection destination et son ordre de traitement ;
- le passage « nom de colonne normalisé → champ métier » ;
- les références à résoudre (`budget_id`, `beneficiaire_id`) ;
- la clé naturelle, garantie d'idempotence : réimporter remplace, ne double
  jamais ;
- les énumérations que le métier tolère.

Seuls les champs déclarés dans `champs` et les références résolues sont écrits :
une colonne non reconnue est ignorée, mais reste consultable dans
`importations_nettoyees`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

# Valeurs imposées par le métier — cf. `dashboard_service` et
# `remboursement_service`, qui les consomment en comparaison littérale.
NATURE_LFI = "lfi"
NATURE_LFR = "lfr"
NATURES = (NATURE_LFI, NATURE_LFR)
PHASES_EXECUTION = ("engagement", "liquidation", "ordonnancement", "paiement")
STATUTS_REMBOURSEMENT = (
    "valide", "paye", "refuse", "soumis", "a_completer", "en_cours",
    "en_attente",
)
SITUATIONS_BENEFICIAIRE = ("actif", "pensionne")


@dataclass(frozen=True)
class Reference:
    """Champ métier à produire depuis une autre collection."""

    champ: str
    type: str
    colonnes: tuple[str, ...]


@dataclass(frozen=True)
class CibleImportation:
    cle: str
    collection: str
    titres_feuilles: tuple[str, ...]
    ordre: int
    cles: tuple[str, ...]
    champs: dict[str, str]
    references: tuple[Reference, ...] = ()
    enums: dict[str, tuple[str, ...]] = field(default_factory=dict)
    #: Colonnes alternatives admises, `colonne alternative → colonne canonique`.
    #: Une même donnée peut être libellée de plusieurs façons dans le métier
    #: (`Montant accordé` / `Montant accordé(e)`), mais le champ reste unique.
    alias: dict[str, str] = field(default_factory=dict)
    traitement_final: Callable[[dict], None] = lambda doc: None

    @property
    def colonnes_reference(self) -> tuple[str, ...]:
        return tuple(c for ref in self.references for c in ref.colonnes)


def appliquer_alias(cible: CibleImportation, valeurs: dict) -> dict:
    """Ajoute aux valeurs les colonnes alternatives, sous leur nom canonique."""
    if not cible.alias:
        return valeurs
    for alternative, canonique in cible.alias.items():
        if alternative in valeurs and canonique not in valeurs:
            valeurs[canonique] = valeurs[alternative]
    return valeurs


def _renseigner_created_at(doc: dict) -> None:
    """Recense le bénéficiaire à sa date d'inscription (filtre du tableau de bord)."""
    if isinstance(doc.get("created_at"), datetime):
        return
    inscrit = doc.get("date_inscription")
    if isinstance(inscrit, datetime):
        doc["created_at"] = inscrit
    elif isinstance(doc.get("exercice"), int):
        doc["created_at"] = datetime(doc["exercice"], 1, 1, tzinfo=timezone.utc)
    else:
        doc["created_at"] = datetime.now(timezone.utc)


def _stamp(donnees: dict) -> None:
    maintenant = datetime.now(timezone.utc)
    donnees.setdefault("created_at", maintenant)
    donnees["updated_at"] = maintenant


CIBLES: tuple[CibleImportation, ...] = (
    CibleImportation(
        cle="beneficiaires",
        collection="beneficiaires",
        titres_feuilles=("beneficiaires",),
        ordre=10,
        cles=("matricule",),
        champs={
            "matricule": "matricule",
            "nom": "nom",
            "prenom": "prenom",
            "date_de_naissance": "date_naissance",
            "genre": "genre",
            "situation": "situation",
            "categorie": "categorie",
            "statut_dossier": "statut_dossier",
            "direction": "direction",
            "region": "adresse.region",
            "district": "adresse.district",
            "commune": "adresse.commune",
            "cin": "cin",
            "montant_cotisation": "montant_cotisation",
            "date_d_inscription": "date_inscription",
            "exercice": "exercice",
        },
        enums={"situation": SITUATIONS_BENEFICIAIRE},
        traitement_final=_renseigner_created_at,
    ),
    CibleImportation(
        cle="budgets_rfm",
        collection="budgets_rfm",
        titres_feuilles=("budget", "budgets", "budgets_rfm"),
        ordre=20,
        cles=("exercice", "chapitre", "ligne_budgetaire", "nature"),
        champs={
            "exercice": "exercice",
            "chapitre": "chapitre",
            "ligne_budgetaire": "ligne_budgetaire",
            "libelle": "libelle",
            "nature": "nature",
            "type": "type",
            "montant_vote": "montant_vote",
        },
        enums={"nature": NATURES},
        traitement_final=_stamp,
    ),
    CibleImportation(
        cle="executions",
        collection="executions",
        titres_feuilles=("executions", "execution", "executions_budgetaires"),
        ordre=30,
        cles=("budget_id", "mois", "phase"),
        champs={
            "mois": "mois",
            "phase": "phase",
            "montant": "montant",
        },
        references=(
            Reference(
                champ="budget_id",
                type="budget",
                colonnes=("exercice", "ligne_budgetaire", "nature"),
            ),
        ),
        enums={"phase": PHASES_EXECUTION, "nature": NATURES},
        traitement_final=_stamp,
    ),
    CibleImportation(
        cle="remboursements",
        collection="remboursements",
        titres_feuilles=("remboursements", "remboursement"),
        ordre=40,
        cles=("numero_dossier",),
        champs={
            "numero_dossier": "numero_dossier",
            "type_prestation": "type_prestation",
            "circuit": "circuit",
            "date_demande": "date_demande",
            "date_decision": "date_decision",
            "montant_demande": "montant_demande",
            "montant_accorde": "montant_accordee",
            "montant_paye": "montant_paye",
            "statut": "statut",
            "motif_refus": "motif_refus",
        },
        references=(
            Reference(
                champ="beneficiaire_id",
                type="beneficiaire",
                colonnes=("matricule",),
            ),
        ),
        enums={"statut": STATUTS_REMBOURSEMENT},
        alias={
            "montant_accordee": "montant_accorde",
            "n_dossier": "numero_dossier",
        },
        traitement_final=_stamp,
    ),
)

CIBLES_PAR_CLE: dict[str, CibleImportation] = {c.cle: c for c in CIBLES}


def cible_pour_feuille(titre: str) -> CibleImportation | None:
    """Résout le titre d'une feuille en cible, via la normalisation de colonne."""
    from app.imports.colonnes import normaliser_nom_colonne

    normalise = normaliser_nom_colonne(titre)
    for cible in CIBLES:
        if normalise in cible.titres_feuilles:
            return cible
    return None


def assigner(document: dict[str, Any], chemin: str, valeur: Any) -> None:
    """Affecte une valeur sur un chemin éventuellement imbriqué (`adresse.region`)."""
    cotes = chemin.split(".")
    cible = document
    for cote in cotes[:-1]:
        existant = cible.get(cote)
        if not isinstance(existant, dict):
            existant = {}
            cible[cote] = existant
        cible = existant
    cible[cotes[-1]] = valeur


def construire_document(
    cible: CibleImportation,
    valeurs: dict[str, Any],
) -> dict[str, Any]:
    """Construit le document métier à partir d'une ligne normalisée.

    Seuls les champs déclarés sont écrits, aux noms attendus par les services.
    """
    document: dict[str, Any] = {}
    for colonne, chemin in cible.champs.items():
        if colonne in valeurs and valeurs[colonne] is not None:
            assigner(document, chemin, valeurs[colonne])
    for reference in cible.references:
        if reference.champ in valeurs and valeurs[reference.champ] is not None:
            document[reference.champ] = valeurs[reference.champ]
    cible.traitement_final(document)
    return document
