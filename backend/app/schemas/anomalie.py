"""Schémas (Pydantic) des requêtes du module de détection d'anomalies."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class ParametresIQR(BaseModel):
    facteur: float = Field(default=1.5, ge=0.0, description="Multiplicateur de l'écart interquartile.")


class ParametresZScore(BaseModel):
    seuil: float = Field(default=3.0, ge=0.0, description="Seuil d'écart réduit.")


class ParametresIsolationForest(BaseModel):
    contamination: float = Field(default=0.05, gt=0.0, description="Proportion attendue d'observations atypiques.")
    graine: int = Field(default=42, description="Graine aléatoire (reproductibilité).")
    n_estimateurs: int = Field(default=100, ge=10, description="Nombre d'arbres d'isolation.")


class ParametresLOF(BaseModel):
    contamination: float = Field(default=0.05, gt=0.0, description="Proportion attendue d'observations atypiques.")
    voisins: Optional[int] = Field(default=None, ge=2, description="Nombre de voisins (défaut : borné au volume).")


class ParametresDetection(BaseModel):
    iqr: Optional[ParametresIQR] = None
    zscore: Optional[ParametresZScore] = None
    isolation_forest: Optional[ParametresIsolationForest] = None
    lof: Optional[ParametresLOF] = None


class RequeteDetection(BaseModel):
    """Paramètres de l'exécution de la détection.

    Tous les champs sont facultatifs : les valeurs par défaut garantissent
    une détection raisonnable sur la nature des données disponibles.
    """

    exercice: Optional[int] = Field(default=None, ge=1900, le=2100)
    variables: Optional[list[str]] = None
    methodes: Optional[list[str]] = None
    parametres: Optional[ParametresDetection] = None
    stocker: bool = Field(default=True, description="Persiste les alertes (workflow de vérification).")


class RequeteVerification(BaseModel):
    """Mise à jour du statut de vérification d'une alerte."""

    statut_verification: str = Field(description="Nouveau statut du workflow de vérification.")
    commentaire: Optional[str] = Field(default=None, max_length=2000)