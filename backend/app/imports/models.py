"""Modèles du système d'importation."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Optional

from pydantic import BaseModel, Field


class OptionsImportation(BaseModel):
    """Options optionnelles de l'importation."""

    encodage: Optional[str] = None
    delimiteur: Optional[str] = None
    feuille: int = 0
    colonnes_obligatoires: list[str] = Field(default_factory=list)
    #: Quand `True`, les feuilles dont l'onglet correspond à une cible
    #: métier sont déversées dans `beneficiaires`/`budgets_rfm`/
    #: `executions`/`remboursements`.
    deversement: bool = False


@dataclass
class ColonneAnalysee:
    nom_original: str
    nom_normalise: str
    type_detecte: str
    nb_lignes: int
    nb_vides: int
    nb_non_vides: int
    nb_invalides: int
    exemples: list[str] = field(default_factory=list)
    #: Index d'onglet d'où provient la colonne (0-based).
    feuille: int = 0


@dataclass
class RejetImportation:
    ligne: int
    colonne: str
    valeur: str
    raison: str
    type_erreur: str
    #: Index d'onglet du classeur (0-based). Utile quand un import traite
    #: plusieurs feuilles à la fois.
    feuille: int = 0


@dataclass
class RapportImportation:
    fichier_original: str
    format: str
    taille_octets: int
    sha256: str
    encodage: Optional[str]
    delimiteur: Optional[str]
    nb_colonnes: int
    nb_lignes_total: int
    nb_lignes_importees: int
    nb_lignes_rejetees: int
    nb_doublons: int
    colonnes: list[ColonneAnalysee] = field(default_factory=list)
    rejets: list[RejetImportation] = field(default_factory=list)
    #: Détail par feuille traitée (une entrée par onglet du classeur).
    feuilles: list[dict] = field(default_factory=list)
    #: Synthèse du déversement vers les collections métier, ou `None`
    #: quand l'option est désactivée.
    deversement: Optional[dict] = None

    def resume(self) -> dict:
        return asdict(self)


# Champs calculés par le pipeline mais exprimés ici pour clarté du typage.
ResultatImportation = dict[str, Any]