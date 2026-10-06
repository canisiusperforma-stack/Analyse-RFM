"""Analyse des remboursements : vue temporelle et statistiques (Data Science).

Fournit la vue « Analyse temporelle » : série mensuelle (évolution) des
demandes et des paiements d'un exercice, moyenne mensuelle, taux
d'exécution (montants remboursés / montants demandés), variations d'un
mois sur l'autre et comparaison avec l'exercice précédent.

Fournit la vue « Statistiques » (module Data Science basé sur
Pandas/NumPy) : statistiques descriptives (moyenne, médiane, variance,
écart-type, quartiles, min/max), distributions, percentiles, corrélations
et comparaison actifs/pensionnés.

Conventions : la période est le mois de la demande (`date_demande`). Les
montants remboursés correspondent aux documents au statut « paye ». La
moyenne mensuelle correspond au total divisé par les 12 mois de
l'exercice. Les taux sont renvoyés en proportion (0.62 = 62 %). La
variance et l'écart-type sont ceux de l'échantillon (ddof=1).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

import numpy as np
import pandas as pd

from app.database import obtenir_database
from app.services.remboursement_service import (
    COLLECTION_BENEFICIAIRES,
    COLLECTION_REMBOURSEMENTS,
    STATUTS_ACCEPTES,
    _acroissir,
    _entete,
    _mois_de_lexercice,
    _montant,
    exercices_remboursements,
)

LIBELLES_MOIS = [
    "Janv.", "Févr.", "Mars", "Avr.", "Mai", "Juin",
    "Juil.", "Août", "Sept.", "Oct.", "Nov.", "Déc.",
]

STATUT_PAYE = "paye"


def _proportion(numérateur: float, dénominateur: float) -> Optional[float]:
    if dénominateur:
        return round(numérateur / dénominateur, 4)
    return None


def _comparer(courant: float, precedent: Optional[float]):
    precedent = precedent if precedent is not None else 0.0
    ecart = _acroissir(courant - precedent) if isinstance(courant, float) else courant - precedent
    variation = (
        _proportion(ecart, precedent) if precedent else None
    )
    return {"courant": courant, "precedent": precedent, "ecart": ecart, "variation_pct": variation}


async def _serie_mensuelle(exercice: int) -> dict[int, dict[str, Any]]:
    """Agrégats mensuels (par date de demande) pour un exercice."""
    db = obtenir_database()
    debut, fin = _entete(exercice)
    filtre_periode = {"date_demande": {"$gte": debut, "$lt": fin}}

    par_mois = {
        mois: {
            "demandes": 0,
            "montant_demande": 0.0,
            "payes": 0,
            "montant_paye": 0.0,
        }
        for mois in range(1, 13)
    }

    cursor = db[COLLECTION_REMBOURSEMENTS].aggregate([
        {"$match": filtre_periode},
        {
            "$group": {
                "_id": {"$month": "$date_demande"},
                "demandes": {"$sum": 1},
                "montant_demande": {"$sum": "$montant_demande"},
                "payes": {
                    "$sum": {"$cond": [{"$eq": ["$statut", STATUT_PAYE]}, 1, 0]}
                },
                "montant_paye": {
                    "$sum": {
                        "$cond": [
                            {"$eq": ["$statut", STATUT_PAYE]},
                            {"$ifNull": ["$montant_paye", 0]},
                            0,
                        ]
                    }
                },
            }
        },
    ])
    async for doc in cursor:
        numero_mois = int(doc["_id"])
        par_mois[numero_mois] = {
            "demandes": int(doc["demandes"]),
            "montant_demande": _acroissir(_montant(doc, "montant_demande")),
            "payes": int(doc["payes"]),
            "montant_paye": _acroissir(_montant(doc, "montant_paye")),
        }
    return par_mois


async def _bilan_exercice(exercice: int) -> dict[str, Any]:
    """Synthèse d'un exercice à partir de la série mensuelle."""
    par_mois = await _serie_mensuelle(exercice)

    evolution: list[dict[str, Any]] = []
    precedent_item: Optional[dict[str, Any]] = None
    for numero_mois in range(1, 13):
        agregat = par_mois[numero_mois]
        demandes = agregat["demandes"]
        moyenne = (
            _acroissir(agregat["montant_demande"] / demandes)
            if demandes else 0.0
        )
        moyenne_paye = (
            _acroissir(agregat["montant_paye"] / agregat["payes"])
            if agregat["payes"] else 0.0
        )

        def _mois_variation(courant, precedent):
            return (
                _proportion(courant - precedent, precedent)
                if precedent_item is not None and precedent
                else None
            )

        evolution.append({
            "mois": numero_mois,
            "periode": f"{exercice:04d}-{numero_mois:02d}",
            "libelle": LIBELLES_MOIS[numero_mois - 1],
            "demandes": demandes,
            "montant_demande": agregat["montant_demande"],
            "montant_paye": agregat["montant_paye"],
            "payes": agregat["payes"],
            "moyenne": moyenne,
            "moyenne_paye": moyenne_paye,
            "taux_execution": _proportion(
                agregat["montant_paye"], agregat["montant_demande"]
            ),
            "variation_demandes": _mois_variation(
                demandes,
                precedent_item["demandes"] if precedent_item else None,
            ),
            "variation_montant": _mois_variation(
                agregat["montant_demande"],
                precedent_item["montant_demande"] if precedent_item else None,
            ),
            "variation_paye": _mois_variation(
                agregat["montant_paye"],
                precedent_item["montant_paye"] if precedent_item else None,
            ),
        })
        precedent_item = evolution[-1]

    demandes = sum(item["demandes"] for item in evolution)
    payes = sum(item["payes"] for item in evolution)
    montant_demande = _acroissir(sum(item["montant_demande"] for item in evolution))
    montant_paye = _acroissir(sum(item["montant_paye"] for item in evolution))

    synthese = {
        "exercice": exercice,
        "demandes": demandes,
        "payes": payes,
        "montant_demande": montant_demande,
        "montant_paye": montant_paye,
        "taux_execution": _proportion(montant_paye, montant_demande),
        "moyenne": _acroissir(montant_demande / demandes) if demandes else 0.0,
        "moyenne_paye": _acroissir(montant_paye / payes) if payes else 0.0,
        "moyenne_mensuelle": {
            "demandes": _acroissir(demandes / 12),
            "payes": _acroissir(payes / 12),
            "montant_demande": _acroissir(montant_demande / 12),
            "montant_paye": _acroissir(montant_paye / 12),
        },
    }
    return {"synthese": synthese, "evolution": evolution}


async def analyse_temporelle(
    exercice: Optional[int] = None,
) -> dict[str, Any]:
    """Évolution mensuelle, moyennes, taux d'exécution et comparaison."""
    if exercice is None:
        disponibles = await exercices_remboursements()
        exercice = disponibles[0] if disponibles else datetime.now(timezone.utc).year
    exercice = int(exercice)

    courant = await _bilan_exercice(exercice)
    exercice_precedent = exercice - 1
    precedent = await _bilan_exercice(exercice_precedent)

    s_courant = courant["synthese"]
    s_precedent = precedent["synthese"]

    retour = {
        "exercice": exercice,
        "calcule_le": datetime.now(timezone.utc).isoformat(),
        "evolution": courant["evolution"],
        "evolution_precedente": precedent["evolution"],
        "synthese": s_courant,
        "comparaison": {
            "exercice_precedent": exercice_precedent,
            "demandes": _comparer(s_courant["demandes"], s_precedent["demandes"]),
            "payes": _comparer(s_courant["payes"], s_precedent["payes"]),
            "montant_demande": _comparer(
                s_courant["montant_demande"], s_precedent["montant_demande"]
            ),
            "montant_paye": _comparer(
                s_courant["montant_paye"], s_precedent["montant_paye"]
            ),
            "moyenne": _comparer(s_courant["moyenne"], s_precedent["moyenne"]),
            "taux_execution": {
                "courant": s_courant["taux_execution"],
                "precedent": s_precedent["taux_execution"],
                "ecart": _acroissir(
                    (s_courant["taux_execution"] or 0.0)
                    - (s_precedent["taux_execution"] or 0.0)
                ),
            },
            "moyenne_mensuelle": {
                "courant": s_courant["moyenne_mensuelle"],
                "precedent": s_precedent["moyenne_mensuelle"],
                "demandes": _comparer(
                    s_courant["moyenne_mensuelle"]["demandes"],
                    s_precedent["moyenne_mensuelle"]["demandes"],
                ),
                "montant_demande": _comparer(
                    s_courant["moyenne_mensuelle"]["montant_demande"],
                    s_precedent["moyenne_mensuelle"]["montant_demande"],
                ),
                "montant_paye": _comparer(
                    s_courant["moyenne_mensuelle"]["montant_paye"],
                    s_precedent["moyenne_mensuelle"]["montant_paye"],
                ),
            },
        },
    }
    return retour


# ---------------------------------------------------------------------------
# Statistiques (module Data Science, Pandas/NumPy)
# ---------------------------------------------------------------------------

LABELS_VARIABLES = {
    "montant_demande": "Montant demandé",
    "montant_accordee": "Montant accordé",
    "montant_paye": "Montant remboursé",
    "delai_jours": "Délai de traitement (jours)",
    "age_beneficiaire": "Âge du bénéficiaire",
}

COLONNES_NUMERIQUES = (
    "montant_demande",
    "montant_accordee",
    "montant_paye",
    "delai_jours",
    "age_beneficiaire",
)

PERCENTILES_ABSCISSES = (1, 5, 10, 25, 50, 75, 90, 95, 99)

VARIABLES_HISTOGRAMME = ("montant_demande", "montant_paye")


async def _charger_dataframe(exercice: int) -> pd.DataFrame:
    """DataFrame Pandas des demandes d'un exercice (avec le bénéficiaire)."""
    db = obtenir_database()
    debut, fin = _entete(exercice)
    cursor = db[COLLECTION_REMBOURSEMENTS].aggregate([
        {"$match": {"date_demande": {"$gte": debut, "$lt": fin}}},
        {
            "$lookup": {
                "from": COLLECTION_BENEFICIAIRES,
                "localField": "beneficiaire_id",
                "foreignField": "_id",
                "as": "beneficiaire",
            }
        },
        {"$unwind": {"path": "$beneficiaire", "preserveNullAndEmptyArrays": True}},
    ])

    lignes = []
    for doc in await cursor.to_list(length=None):
        beneficiaire = doc.get("beneficiaire") or {}
        date_demande = doc.get("date_demande")
        date_decision = doc.get("date_decision")
        date_naissance = beneficiaire.get("date_naissance")

        delai = None
        if date_demande and date_decision:
            delai = float((date_decision - date_demande).days)

        age = None
        if date_demande and date_naissance:
            age = (date_demande - date_naissance).days / 365.25

        montant_accordee = (
            _montant(doc, "montant_accordee")
            if doc.get("montant_accordee") is not None else None
        )
        montant_paye = (
            _montant(doc, "montant_paye")
            if doc.get("statut") == "paye" and doc.get("montant_paye") is not None
            else None
        )

        lignes.append({
            "montant_demande": _montant(doc, "montant_demande"),
            "montant_accordee": montant_accordee,
            "montant_paye": montant_paye,
            "delai_jours": delai,
            "age_beneficiaire": age,
            "statut": doc.get("statut"),
            "type_prestation": doc.get("type_prestation"),
            "circuit": doc.get("circuit"),
            "situation": beneficiaire.get("situation"),
            "genre": beneficiaire.get("genre"),
        })

    dataframe = pd.DataFrame(lignes)
    if dataframe.empty:
        return dataframe
    for colonne in COLONNES_NUMERIQUES:
        dataframe[colonne] = pd.to_numeric(dataframe[colonne], errors="coerce")
    return dataframe


def _arrondir(valeur, decimales: int = 2):
    if valeur is None:
        return None
    try:
        return round(float(valeur), decimales)
    except (TypeError, ValueError):
        return None


def _descriptives(valeurs) -> dict[str, Any]:
    arr = np.asarray(
        [v for v in valeurs if v is not None and not (isinstance(v, float) and np.isnan(v))],
        dtype=float,
    )
    if arr.size == 0:
        return {
            "nombre": 0, "moyenne": None, "mediane": None, "variance": None,
            "ecart_type": None, "minimum": None, "maximum": None,
            "quartiles": {"q1": None, "mediane": None, "q3": None}, "somme": None,
        }
    q1, mediane, q3 = np.percentile(arr, [25, 50, 75])
    return {
        "nombre": int(arr.size),
        "moyenne": _arrondir(arr.mean()),
        "mediane": _arrondir(mediane),
        "variance": _arrondir(arr.var(ddof=1)),
        "ecart_type": _arrondir(arr.std(ddof=1)),
        "minimum": _arrondir(arr.min()),
        "maximum": _arrondir(arr.max()),
        "quartiles": {
            "q1": _arrondir(q1),
            "mediane": _arrondir(mediane),
            "q3": _arrondir(q3),
        },
        "somme": _arrondir(arr.sum()),
    }


def _distribution(valeurs, classes: int = 5) -> list[dict[str, Any]]:
    arr = np.asarray(
        [v for v in valeurs if v is not None and not (isinstance(v, float) and np.isnan(v))],
        dtype=float,
    )
    if arr.size == 0:
        return []
    if arr.min() >= arr.max():
        bornes = [float(arr.min()), float(arr.min()) + 1.0]
        effectifs = [int(arr.size)]
    else:
        effectifs, bornes = np.histogram(arr, bins=classes)
    total = int(sum(effectifs))
    classes_resultat = []
    for index in range(len(bornes) - 1):
        borne_inf = round(float(bornes[index]), 2)
        borne_sup = round(float(bornes[index + 1]), 2)
        classes_resultat.append({
            "borne_inf": borne_inf,
            "borne_sup": borne_sup,
            "intervalle": (
                f"[{borne_inf:,.0f} ; {borne_sup:,.0f}["
                if index < len(bornes) - 2 else
                f"[{borne_inf:,.0f} ; {borne_sup:,.0f}]"
            ),
            "effectif": int(effectifs[index]),
            "pourcentage": round(effectifs[index] / total, 4) if total else 0.0,
        })
    return classes_resultat


def _percentiles(valeurs) -> dict[str, Optional[float]]:
    arr = np.asarray(
        [v for v in valeurs if v is not None and not (isinstance(v, float) and np.isnan(v))],
        dtype=float,
    )
    if arr.size == 0:
        return {str(p): None for p in PERCENTILES_ABSCISSES}
    return {
        str(p): _arrondir(np.percentile(arr, p), 2) for p in PERCENTILES_ABSCISSES
    }


def _correlations(dataframe: pd.DataFrame) -> dict[str, Any]:
    presentes = [
        colonne for colonne in COLONNES_NUMERIQUES
        if colonne in dataframe.columns
        and dataframe[colonne].notna().sum() >= 2
    ]
    matrice: dict[str, dict[str, Optional[float]]] = {colonne: {} for colonne in presentes}
    if len(presentes) < 2:
        return {"matrice": matrice, "pertinentes": []}

    coefficients = dataframe[presentes].corr().to_dict()
    paires: list[dict[str, Any]] = []
    for i, colonne_a in enumerate(presentes):
        for colonne_b in presentes[i + 1:]:
            valeur = coefficients.get(colonne_a, {}).get(colonne_b)
            if valeur is None or (isinstance(valeur, float) and np.isnan(valeur)):
                valeur = None
            matrice[colonne_a][colonne_b] = _arrondir(valeur, 4)
            matrice[colonne_b][colonne_a] = _arrondir(valeur, 4)
            if valeur is not None:
                paires.append({
                    "a": colonne_a,
                    "b": colonne_b,
                    "correlation": round(float(valeur), 4),
                    "intensite": (
                        "forte" if abs(valeur) >= 0.7
                        else "moyenne" if abs(valeur) >= 0.4
                        else "faible"
                    ),
                })
    paires.sort(key=lambda paire: abs(paire["correlation"]), reverse=True)
    return {
        "matrice": matrice,
        "pertinentes": paires[:8],
    }


def _taux_acceptation(documents) -> Optional[float]:
    acceptees = sum(1 for doc in documents if doc.get("statut") in STATUTS_ACCEPTES)
    rejetees = sum(1 for doc in documents if doc.get("statut") == "refuse")
    if (acceptees + rejetees) == 0:
        return None
    return round(acceptees / (acceptees + rejetees), 4)


async def _statistiques_par_situation(dataframe: pd.DataFrame) -> dict[str, Any]:
    def _groupe(situation: str) -> dict[str, Any]:
        sous = dataframe[dataframe["situation"] == situation]
        return {
            "dossiers": int(len(sous)),
            "montant_demande": _arrondir(
                sous["montant_demande"].sum() if not sous.empty else 0.0
            ),
            "moyenne": _arrondir(
                sous["montant_demande"].mean() if not sous.empty else 0.0
            ),
            "montant_paye": _arrondir(
                sous["montant_paye"].sum() if not sous.empty else 0.0
            ),
            "moyenne_paye": _arrondir(
                sous["montant_paye"].mean() if not sous.empty else 0.0
            ),
            "taux_acceptation": _taux_acceptation(sous.to_dict("records")),
        }

    actifs = _groupe("actif")
    pensionnes = _groupe("pensionne")

    metriques = [
        ("dossiers", "Dossiers déposés", "entier"),
        ("montant_demande", "Montant demandé", "montant"),
        ("moyenne", "Montant moyen par dossier", "montant"),
        ("montant_paye", "Montant remboursé", "montant"),
        ("moyenne_paye", "Montant moyen remboursé", "montant"),
        ("taux_acceptation", "Taux d'acceptation", "taux"),
    ]
    comparaison = []
    for cle, label, type_valeur in metriques:
        valeur_actifs = actifs[cle]
        valeur_pensionnes = pensionnes[cle]
        ecart = _arrondir(
            (valeur_actifs or 0.0) - (valeur_pensionnes or 0.0)
        )
        ratio = (
            round(valeur_actifs / valeur_pensionnes, 4)
            if valeur_pensionnes
            else None
        )
        comparaison.append({
            "cle": cle,
            "label": label,
            "type": type_valeur,
            "actifs": valeur_actifs,
            "pensionnes": valeur_pensionnes,
            "ecart": ecart,
            "ratio": ratio,
        })

    db = obtenir_database()
    effectifs = {}
    if not dataframe.empty:
        for situation in ("actif", "pensionne"):
            effectifs[situation] = await db[
                COLLECTION_BENEFICIAIRES
            ].count_documents({"situation": situation})

    return {
        "actifs": actifs,
        "pensionnes": pensionnes,
        "comparaison": comparaison,
        "effectifs_population": effectifs,
    }


async def statistiques_data_science(
    exercice: Optional[int] = None,
) -> dict[str, Any]:
    """Statistiques descriptives, distributions, corrélations et actifs/pensionnés."""
    if exercice is None:
        disponibles = await exercices_remboursements()
        exercice = disponibles[0] if disponibles else datetime.now(timezone.utc).year
    exercice = int(exercice)

    dataframe = await _charger_dataframe(exercice)

    descriptives = {
        colonne: _descriptives(
            dataframe[colonne].tolist() if not dataframe.empty else []
        )
        for colonne in COLONNES_NUMERIQUES
    }

    distributions = {
        colonne: _distribution(
            dataframe[colonne].tolist() if not dataframe.empty else []
        )
        for colonne in VARIABLES_HISTOGRAMME
    }

    percentiles = {
        colonne: _percentiles(
            dataframe[colonne].tolist() if not dataframe.empty else []
        )
        for colonne in VARIABLES_HISTOGRAMME
    }

    correlations = _correlations(dataframe)
    actifs_pensionnes = await _statistiques_par_situation(dataframe)

    return {
        "exercice": exercice,
        "methode": f"Pandas {pd.__version__} + NumPy {np.__version__}",
        "calcule_le": datetime.now(timezone.utc).isoformat(),
        "nombre_documents": int(len(dataframe)),
        "variables": LABELS_VARIABLES,
        "descriptives": descriptives,
        "distributions": distributions,
        "percentiles": percentiles,
        "correlations": correlations,
        "actifs_pensionnes": actifs_pensionnes,
    }