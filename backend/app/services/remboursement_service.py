"""Analyse des remboursements par exercice (agrégations MongoDB).

Fournit la vue « Remboursements » : volumes par statut, montants
(totaux, moyennes, médianes, minimums, maximums), répartitions par type
de dépense et par circuit, série mensuelle et comparaison avec
l'exercice précédent, ainsi qu'une liste filtrable, triable et paginée
(avec recherche sur n° de dossier et sur le bénéficiaire).

Conventions : l'exercice est déduit de `date_demande`. La médiane est
calculée en Python à partir des montants agrégés (opérateur absent dans
les $group des versions antérieures de MongoDB).
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional

from bson import Decimal128, ObjectId

from app.database import obtenir_database

COLLECTION_REMBOURSEMENTS = "remboursements"
COLLECTION_BENEFICIAIRES = "beneficiaires"

STATUT_ACCEPTE = "valide"
STATUT_PAYE = "paye"
STATUT_REFUSE = "refuse"

STATUTS_ACCEPTES = ("valide", "paye")
STATUTS_EN_ATTENTE = ("soumis", "a_completer", "en_cours", "en_attente")

TRI_VALEURS = (
    "numero_dossier",
    "date_demande",
    "montant_demande",
    "statut",
    "type_prestation",
    "beneficiaire",
    "montant_paye",
)


def _montant(document: dict[str, Any], champ: str) -> float:
    valeur = document.get(champ)
    if valeur is None:
        return 0.0
    if isinstance(valeur, Decimal128):
        return float(valeur.to_decimal())
    if isinstance(valeur, Decimal):
        return float(valeur)
    return float(valeur)


def _acroissir(montant: float) -> float:
    return round(montant, 2)


def _mediane(valeurs: list[float]) -> Optional[float]:
    propres = [v for v in valeurs if v is not None]
    if not propres:
        return None
    propres.sort()
    milieu = len(propres) // 2
    if len(propres) % 2 == 1:
        return propres[milieu]
    return (propres[milieu - 1] + propres[milieu]) / 2


def _entete(exercice: int) -> tuple[datetime, datetime]:
    return (
        datetime(exercice, 1, 1, tzinfo=timezone.utc),
        datetime(exercice + 1, 1, 1, tzinfo=timezone.utc),
    )


def _mois_de_lexercice(exercice: int) -> list[str]:
    return [f"{exercice:04d}-{mois:02d}" for mois in range(1, 13)]


def _texte(valeur) -> Optional[str]:
    if not isinstance(valeur, str):
        return None
    valeur = valeur.strip()
    return valeur or None


async def exercices_remboursements() -> list[int]:
    """Exercices présents dans les demandes (date de demande), décroissant."""
    db = obtenir_database()
    exercices: set[int] = set()
    cursor = db[COLLECTION_REMBOURSEMENTS].aggregate([
        {"$group": {"_id": {"$year": "$date_demande"}}}
    ])
    async for doc in cursor:
        exercices.add(int(doc["_id"]))
    return sorted(exercices, reverse=True)


async def _agregats_montants(
    filtre: dict[str, Any], champ: str
) -> dict[str, Any]:
    """total, moyenne, médiane, minimum, maximum d'un champ de montant."""
    db = obtenir_database()
    agg = {
        "total": {"$sum": 1},
        "somme": {"$sum": f"${champ}"},
        "minimum": {"$min": f"${champ}"},
        "maximum": {"$max": f"${champ}"},
        "valeurs": {"$push": f"${champ}"},
    }
    resultat = {
        "montants": 0,
        "total": 0.0,
        "moyenne": 0.0,
        "mediane": None,
        "minimum": 0.0,
        "maximum": 0.0,
    }
    cursor = db[COLLECTION_REMBOURSEMENTS].aggregate([
        {"$match": filtre},
        {"$group": {"_id": None, **agg}},
    ])
    async for doc in cursor:
        valeurs = [v for v in doc.get("valeurs", []) if v is not None]
        montants = [
            float(v.to_decimal()) if isinstance(v, Decimal128) else float(v)
            for v in valeurs
        ]
        resultat = {
            "montants": len(montants),
            "total": _acroissir(_montant(doc, "somme")),
            "moyenne": _acroissir(
                _montant(doc, "somme") / len(montants) if montants else 0.0
            ),
            "mediane": _acroissir(_mediane(montants)) if montants else None,
            "minimum": _acroissir(min(montants)) if montants else 0.0,
            "maximum": _acroissir(max(montants)) if montants else 0.0,
        }
    return resultat


async def statistiques_remboursements(
    exercice: Optional[int] = None,
) -> dict[str, Any]:
    """Indicateurs des remboursements d'un exercice (+ comparaison)."""
    if exercice is None:
        disponibles = await exercices_remboursements()
        exercice = disponibles[0] if disponibles else datetime.now(timezone.utc).year
    exercice = int(exercice)
    db = obtenir_database()
    debut, fin = _entete(exercice)
    filtre_periode = {"date_demande": {"$gte": debut, "$lt": fin}}

    async def _compter_statuts(statuts: tuple[str, ...]) -> int:
        if not statuts:
            return 0
        return await db[COLLECTION_REMBOURSEMENTS].count_documents({
            **filtre_periode,
            "statut": {"$in": list(statuts)},
        })

    demandes = await db[COLLECTION_REMBOURSEMENTS].count_documents(filtre_periode)
    acceptees = await _compter_statuts(STATUTS_ACCEPTES)
    rejetees = await _compter_statuts((STATUT_REFUSE,))
    en_attente = await _compter_statuts(STATUTS_EN_ATTENTE)
    payes = await _compter_statuts((STATUT_PAYE,))

    montant_demande = await _agregats_montants(filtre_periode, "montant_demande")
    montant_accordee = await _agregats_montants(
        {**filtre_periode, "statut": {"$in": list(STATUTS_ACCEPTES)}},
        "montant_accordee",
    )
    montant_paye = await _agregats_montants(
        {**filtre_periode, "statut": STATUT_PAYE},
        "montant_paye",
    )

    taux_acceptation = (
        acceptees / (acceptees + rejetees) if (acceptees + rejetees) > 0 else 0.0
    )

    repartition_par_statut: list[dict[str, Any]] = []
    cursor = db[COLLECTION_REMBOURSEMENTS].aggregate([
        {"$match": filtre_periode},
        {"$group": {"_id": "$statut", "total": {"$sum": 1}}},
        {"$sort": {"total": -1}},
    ])
    async for doc in cursor:
        repartition_par_statut.append(
            {"statut": doc["_id"] or "inconnu", "total": int(doc["total"])}
        )

    repartition_par_type: list[dict[str, Any]] = []
    cursor = db[COLLECTION_REMBOURSEMENTS].aggregate([
        {"$match": filtre_periode},
        {
            "$group": {
                "_id": "$type_prestation",
                "total": {"$sum": 1},
                "montant_demande": {"$sum": "$montant_demande"},
                "montant_paye": {"$sum": "$montant_paye"},
            }
        },
        {"$sort": {"total": -1}},
    ])
    async for doc in cursor:
        repartition_par_type.append({
            "type_prestation": doc["_id"] or "inconnue",
            "total": int(doc["total"]),
            "montant_demande": _acroissir(_montant(doc, "montant_demande")),
            "montant_paye": _acroissir(_montant(doc, "montant_paye")),
        })

    repartition_par_circuit: list[dict[str, Any]] = []
    cursor = db[COLLECTION_REMBOURSEMENTS].aggregate([
        {"$match": filtre_periode},
        {"$group": {"_id": "$circuit", "total": {"$sum": 1}}},
        {"$sort": {"total": -1}},
    ])
    async for doc in cursor:
        repartition_par_circuit.append(
            {"circuit": doc["_id"] or "inconnu", "total": int(doc["total"])}
        )

    par_mois: dict[str, dict[str, Any]] = {}
    cursor = db[COLLECTION_REMBOURSEMENTS].aggregate([
        {"$match": filtre_periode},
        {
            "$group": {
                "_id": {"$dateToString": {"format": "%Y-%m", "date": "$date_demande"}},
                "demandes": {"$sum": 1},
                "montant_demande": {"$sum": "$montant_demande"},
            }
        },
        {"$sort": {"_id": 1}},
    ])
    async for doc in cursor:
        mois = doc["_id"]
        par_mois[mois] = {
            "mois": mois,
            "demandes": int(doc["demandes"]),
            "montant_demande": _acroissir(_montant(doc, "montant_demande")),
            "payes": 0,
            "montant_paye": 0.0,
        }

    cursor = db[COLLECTION_REMBOURSEMENTS].aggregate([
        {
            "$match": {
                "date_decision": {"$gte": debut, "$lt": fin},
                "statut": STATUT_PAYE,
            }
        },
        {
            "$group": {
                "_id": {"$dateToString": {"format": "%Y-%m", "date": "$date_decision"}},
                "payes": {"$sum": 1},
                "montant_paye": {"$sum": "$montant_paye"},
            }
        },
        {"$sort": {"_id": 1}},
    ])
    async for doc in cursor:
        mois = doc["_id"]
        if mois not in par_mois:
            par_mois[mois] = {
                "mois": mois,
                "demandes": 0,
                "montant_demande": 0.0,
                "payes": 0,
                "montant_paye": 0.0,
            }
        par_mois[mois]["payes"] = int(doc["payes"])
        par_mois[mois]["montant_paye"] = _acroissir(_montant(doc, "montant_paye"))

    serie_mensuelle = sorted(par_mois.values(), key=lambda item: item["mois"])
    presents = {item["mois"] for item in serie_mensuelle}
    for mois in _mois_de_lexercice(exercice):
        if mois not in presents:
            serie_mensuelle.append({
                "mois": mois,
                "demandes": 0,
                "montant_demande": 0.0,
                "payes": 0,
                "montant_paye": 0.0,
            })
    serie_mensuelle.sort(key=lambda item: item["mois"])

    resultat = {
        "exercice": exercice,
        "calcule_le": datetime.now(timezone.utc).isoformat(),
        "demandes": int(demandes),
        "acceptees": int(acceptees),
        "rejetees": int(rejetees),
        "en_attente": int(en_attente),
        "payes": int(payes),
        "taux_acceptation": round(taux_acceptation, 6),
        "montants": {
            "demande": montant_demande,
            "accordee": montant_accordee,
            "paye": montant_paye,
        },
        "repartition_par_statut": repartition_par_statut,
        "repartition_par_type": repartition_par_type,
        "repartition_par_circuit": repartition_par_circuit,
        "serie_mensuelle": serie_mensuelle,
    }

    resultat["comparaison"] = await _comparaison(exercice, resultat)
    return resultat


async def _comparaison(
    exercice: int,
    courant: dict[str, Any],
) -> Optional[dict[str, Any]]:
    precedents = await exercices_remboursements()
    if (exercice - 1) not in precedents:
        return None
    db = obtenir_database()
    debut, fin = _entete(exercice - 1)
    filtre = {"date_demande": {"$gte": debut, "$lt": fin}}

    montant_demande = 0.0
    cursor = db[COLLECTION_REMBOURSEMENTS].aggregate([
        {"$match": filtre},
        {"$group": {"_id": None, "total": {"$sum": "$montant_demande"}}},
    ])
    async for doc in cursor:
        montant_demande = _montant(doc, "total")

    montant_paye = 0.0
    cursor = db[COLLECTION_REMBOURSEMENTS].aggregate([
        {"$match": {**filtre, "statut": STATUT_PAYE}},
        {"$group": {"_id": None, "total": {"$sum": "$montant_paye"}}},
    ])
    async for doc in cursor:
        montant_paye = _montant(doc, "total")

    precedent = {
        "demandes": await db[COLLECTION_REMBOURSEMENTS].count_documents(filtre),
        "payes": await db[COLLECTION_REMBOURSEMENTS].count_documents(
            {**filtre, "statut": STATUT_PAYE}
        ),
        "montant_demande": _acroissir(montant_demande),
        "montant_paye": _acroissir(montant_paye),
    }
    retour = {
        "exercice_precedent": exercice - 1,
        "demandes": courant["demandes"],
        "payes": courant["payes"],
        "montant_demande": _acroissir(courant["montants"]["demande"]["total"]),
        "montant_paye": _acroissir(courant["montants"]["paye"]["total"]),
        **{f"{cle}_precedent": valeur for cle, valeur in precedent.items()},
        "ecart_demandes": int(courant["demandes"] - precedent["demandes"]),
        "ecart_payes": int(courant["payes"] - precedent["payes"]),
        "ecart_montant_demande": _acroissir(
            courant["montants"]["demande"]["total"] - precedent["montant_demande"]
        ),
        "ecart_montant_paye": _acroissir(
            courant["montants"]["paye"]["total"] - precedent["montant_paye"]
        ),
    }
    for cle in ("demandes", "payes"):
        retour[f"variation_pct_{cle}"] = (
            round(retour[f"ecart_{cle}"] / precedent[cle], 6)
            if precedent[cle] > 0
            else None
        )
    for cle in ("montant_demande", "montant_paye"):
        retour[f"variation_pct_{cle}"] = (
            round(retour[f"ecart_{cle}"] / precedent[cle], 6)
            if precedent[cle] > 0
            else None
        )
    return retour


async def _filtre_liste(
    exercice: int,
    recherche: Optional[str],
    statut: Optional[str],
    type_prestation: Optional[str],
    circuit: Optional[str],
    montant_min: Optional[float],
    montant_max: Optional[float],
) -> list[dict[str, Any]]:
    debut, fin = _entete(exercice)
    filtres: list[dict[str, Any]] = [
        {"date_demande": {"$gte": debut, "$lt": fin}},
    ]
    if statut:
        filtres.append({"statut": statut})
    if type_prestation:
        filtres.append({"type_prestation": type_prestation})
    if circuit:
        filtres.append({"circuit": circuit})
    borne: dict[str, Any] = {}
    if montant_min is not None:
        borne["$gte"] = montant_min
    if montant_max is not None:
        borne["$lte"] = montant_max
    if borne:
        filtres.append({"montant_demande": borne})
    return filtres


async def lister_remboursements(
    exercice: Optional[int] = None,
    recherche: Optional[str] = None,
    statut: Optional[str] = None,
    type_prestation: Optional[str] = None,
    circuit: Optional[str] = None,
    montant_min: Optional[float] = None,
    montant_max: Optional[float] = None,
    tri: str = "date_demande",
    ordre: str = "desc",
    limite: int = 50,
    saut: int = 0,
) -> dict[str, Any]:
    if exercice is None:
        disponibles = await exercices_remboursements()
        exercice = disponibles[0] if disponibles else datetime.now(timezone.utc).year
    exercice = int(exercice)
    db = obtenir_database()
    recherche = _texte(recherche)
    statut = _texte(statut)
    type_prestation = _texte(type_prestation)
    circuit = _texte(circuit)
    if tri not in TRI_VALEURS:
        tri = "date_demande"
    if ordre not in ("asc", "desc"):
        ordre = "desc"

    filtres = await _filtre_liste(
        exercice, recherche, statut, type_prestation, circuit, montant_min, montant_max
    )

    norme = re.compile(re.escape(recherche), re.IGNORECASE) if recherche else None
    def _jointure_beneficiaire() -> list[dict[str, Any]]:
        return [
            {
                "$lookup": {
                    "from": COLLECTION_BENEFICIAIRES,
                    "localField": "beneficiaire_id",
                    "foreignField": "_id",
                    "as": "tout_beneficiaire",
                }
            },
            {
                "$addFields": {
                    "beneficiaire": {
                        "$ifNull": [{"$arrayElemAt": ["$tout_beneficiaire", 0]}, None]
                    }
                }
            },
            {"$project": {"tout_beneficiaire": 0}},
        ]

    etapes = [{"$match": {"$and": filtres}}]
    etapes += _jointure_beneficiaire()

    if norme:
        etapes.append({
            "$match": {
                "$or": [
                    {"numero_dossier": norme},
                    {"beneficiaire.nom": norme},
                    {"beneficiaire.prenom": norme},
                    {"beneficiaire.matricule": norme},
                ]
            }
        })

    compteur = db[COLLECTION_REMBOURSEMENTS].aggregate([
        *etapes,
        {"$count": "total"},
    ])
    total = 0
    async for doc in compteur:
        total = int(doc["total"])

    tri_cle = (
        {"beneficiaire.nom": 1 if ordre == "asc" else -1}
        if tri == "beneficiaire"
        else {tri: 1 if ordre == "asc" else -1}
    )
    page = db[COLLECTION_REMBOURSEMENTS].aggregate([
        *etapes,
        {"$sort": tri_cle},
        {"$skip": saut},
        {"$limit": limite},
        {
            "$project": {
                "_id": 0,
                "numero_dossier": 1,
                "date_demande": 1,
                "date_decision": 1,
                "type_prestation": 1,
                "circuit": 1,
                "montant_demande": 1,
                "montant_accordee": 1,
                "montant_paye": 1,
                "statut": 1,
                "motif_refus": 1,
                "exercice": {"$year": "$date_demande"},
                "beneficiaire": {
                    "$ifNull": [
                        "$beneficiaire",
                        None,
                    ]
                },
            }
        },
    ])

    items: list[dict[str, Any]] = []
    async for doc in page:
        beneficiaire = doc.get("beneficiaire") or {}
        items.append({
            "numero_dossier": doc.get("numero_dossier"),
            "date_demande": doc.get("date_demande"),
            "date_decision": doc.get("date_decision"),
            "type_prestation": doc.get("type_prestation"),
            "circuit": doc.get("circuit"),
            "montant_demande": _montant(doc, "montant_demande"),
            "montant_accordee": (
                _montant(doc, "montant_accordee")
                if doc.get("montant_accordee") is not None
                else None
            ),
            "montant_paye": (
                _montant(doc, "montant_paye")
                if doc.get("montant_paye") is not None
                else None
            ),
            "statut": doc.get("statut"),
            "motif_refus": doc.get("motif_refus"),
            "exercice": doc.get("exercice"),
            "beneficiaire": {
                "matricule": beneficiaire.get("matricule"),
                "nom": beneficiaire.get("nom"),
                "prenom": beneficiaire.get("prenom"),
            },
        })

    return {
        "exercice": exercice,
        "total": total,
        "limite": limite,
        "saut": saut,
        "items": items,
    }