"""Service de détection des observations atypiques (workflow de vérification).

Couche métier entre les routes `anomalies` et le module
`app.ml.anomaly_detection` :
- chargement des remboursements d'un exercice (avec bénéficiaire) ;
- détection par variable et par méthode, avec test de la nature des données ;
- persistance des alertes dans la collection `anomalies` (upsert non
  destructif : le statut de vérification, le commentaire et le traiteur d'une
  alerte déjà connue sont préservés) ;
- listage filtrable/paginé et mise à jour du statut de vérification.

Lexique imposé : « observation atypique », « anomalie potentielle »,
« valeur à vérifier ». Aucune observation n'est jamais qualifiée de fraude.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional

from bson import Decimal128
from bson.objectid import ObjectId
from pymongo import ReturnDocument

from app.database import obtenir_database
from app.ml.anomaly_detection import (
    LABELS_METHODES,
    LABELS_NIVEAUX,
    METHODES,
    MINIMUM_OBSERVATIONS,
    NIVEAUX,
    PARAMETRES_PAR_DEFAUT,
    analyser_variable,
)
from app.services.remboursement_service import (
    COLLECTION_BENEFICIAIRES,
    COLLECTION_REMBOURSEMENTS,
    STATUT_PAYE,
    _entete,
    _montant,
    exercices_remboursements,
)
from app.utils.errors import ErreurNotFound, ErreurValidation
from app.utils.logging import get_logger

logger = get_logger(__name__)

COLLECTION_ANOMALIES = "anomalies"

VARIABLES_ANALYSABLES: dict[str, dict[str, str]] = {
    "montant_demande": {"label": "Montant demandé", "type": "montant"},
    "montant_accordee": {"label": "Montant accordé", "type": "montant"},
    "montant_paye": {"label": "Montant remboursé", "type": "montant"},
    "delai_jours": {"label": "Délai de traitement (jours)", "type": "duree"},
    "age_beneficiaire": {"label": "Âge du bénéficiaire", "type": "age"},
}

TYPE_ANOMALIE_PAR_VARIABLE: dict[str, str] = {
    "montant_demande": "montant_atypique",
    "montant_accordee": "montant_atypique",
    "montant_paye": "montant_atypique",
    "delai_jours": "delai_atypique",
    "age_beneficiaire": "caracteristique_atypique",
}

STATUT_VERIFICATION_INITIAL = "a_verifier"

# Statut de vérification : état du workflow humain, jamais une qualification
# automatique de fraude.
STATUTS_VERIFICATION: dict[str, dict[str, Any]] = {
    "a_verifier": {"label": "À vérifier", "ordre": 0},
    "en_cours": {"label": "En cours de vérification", "ordre": 1},
    "confirmee": {"label": "Atypicité confirmée", "ordre": 2},
    "ecartee": {"label": "Écartée", "ordre": 3},
}

TRI_VALEURS = ("score", "detecte_le", "numero_dossier", "valeur", "niveau")


def _decimal128(valeur: float) -> Decimal128:
    return Decimal128(Decimal(str(round(float(valeur), 2))))


def _en_iso(valeur: Any) -> Any:
    if hasattr(valeur, "isoformat"):
        return valeur.isoformat()
    return valeur


def _serialiser_anomalie(document: dict[str, Any]) -> dict[str, Any]:
    """Document `anomalies` (BSON) → dictionnaire JSON sérialisable."""
    def _id(cle: str) -> Optional[str]:
        valeur = document.get(cle)
        return str(valeur) if valeur is not None else None

    valeur = document.get("valeur")
    retour = dict(document)
    retour["id"] = _id("_id")
    retour.pop("_id", None)
    retour["run_id"] = _id("run_id")
    retour["remboursement_id"] = _id("remboursement_id")
    retour["beneficiaire_id"] = _id("beneficiaire_id")
    retour["traite_par"] = _id("traite_par")
    retour["valeur"] = (
        float(valeur.to_decimal())
        if isinstance(valeur, Decimal128)
        else valeur
    )
    for cle in (
        "date_demande",
        "date_decision",
        "detecte_le",
        "traite_le",
        "created_at",
        "updated_at",
    ):
        retour[cle] = _en_iso(retour.get(cle))
    return retour


async def _charger_observations(exercice: int) -> list[dict[str, Any]]:
    """Remboursements d'un exercice avec bénéficiaire (variables numériques)."""
    db = obtenir_database()
    debut, fin = _entete(exercice)
    cursor = db[COLLECTION_REMBOURSEMENTS].aggregate([
        {"$match": {"date_demande": {"$gte": debut, "$lt": fin}}},
        {
            "$lookup": {
                "from": COLLECTION_BENEFICIAIRES,
                "localField": "beneficiaire_id",
                "foreignField": "_id",
                "as": "b",
            }
        },
        {"$unwind": {"path": "$b", "preserveNullAndEmptyArrays": True}},
    ])

    lignes: list[dict[str, Any]] = []
    for doc in await cursor.to_list(length=None):
        beneficiaire = doc.get("b") or {}
        date_demande = doc.get("date_demande")
        date_decision = doc.get("date_decision")
        date_naissance = beneficiaire.get("date_naissance")

        delai = None
        if date_demande and date_decision:
            delai = (date_decision - date_demande).days

        age = None
        if date_demande and date_naissance:
            age = (date_demande - date_naissance).days / 365.25

        montant_accordee = (
            _montant(doc, "montant_accordee")
            if doc.get("montant_accordee") is not None
            else None
        )
        montant_paye = (
            _montant(doc, "montant_paye")
            if doc.get("statut") == STATUT_PAYE and doc.get("montant_paye") is not None
            else None
        )

        lignes.append({
            "_id": doc["_id"],
            "numero_dossier": doc.get("numero_dossier"),
            "beneficiaire_id": doc.get("beneficiaire_id"),
            "beneficiaire": {
                "matricule": beneficiaire.get("matricule"),
                "nom": beneficiaire.get("nom"),
                "prenom": beneficiaire.get("prenom"),
            },
            "statut_remboursement": doc.get("statut"),
            "type_prestation": doc.get("type_prestation"),
            "date_demande": date_demande,
            "date_decision": date_decision,
            "montant_demande": _montant(doc, "montant_demande"),
            "montant_accordee": montant_accordee,
            "montant_paye": montant_paye,
            "delai_jours": delai,
            "age_beneficiaire": age,
        })
    return lignes


def _construire_document_anomalie(
    observation: dict[str, Any],
    variable: str,
    anomalie: dict[str, Any],
    exercice: int,
    run_id: ObjectId,
    calcule_le: datetime,
) -> dict[str, Any]:
    beneficiaire = observation.get("beneficiaire") or {}
    maintenant = datetime.now(timezone.utc)
    return {
        "exercice": exercice,
        "run_id": run_id,
        "remboursement_id": observation.get("_id"),
        "numero_dossier": observation.get("numero_dossier"),
        "beneficiaire_id": observation.get("beneficiaire_id"),
        "beneficiaire": beneficiaire,
        "date_demande": observation.get("date_demande"),
        "statut_remboursement": observation.get("statut_remboursement"),
        "type_prestation": observation.get("type_prestation"),
        "type_anomalie": TYPE_ANOMALIE_PAR_VARIABLE.get(variable, "observation_atypique"),
        "variable": variable,
        "libelle_variable": VARIABLES_ANALYSABLES[variable]["label"],
        "valeur": _decimal128(anomalie["valeur"]),
        "score": anomalie["score"],
        "niveau": anomalie["niveau"],
        "label_niveau": anomalie["label_niveau"],
        "nombre_methodes": anomalie["nombre_methodes"],
        "methodes_detectees": anomalie["methodes_detectees"],
        "justification": anomalie["justification"],
        "par_methode": anomalie["par_methode"],
        "statut_verification": STATUT_VERIFICATION_INITIAL,
        "label_statut_verification": STATUTS_VERIFICATION[STATUT_VERIFICATION_INITIAL]["label"],
        "commentaire": None,
        "traite_par": None,
        "traite_le": None,
        "detecte_le": calcule_le,
        "created_at": maintenant,
        "updated_at": maintenant,
    }


async def _upsert_anomalie(document: dict[str, Any]) -> Optional[ObjectId]:
    """Insère ou réutilise l'alerte existante (préserve le workflow)."""
    db = obtenir_database()
    filtres = {
        "exercice": document["exercice"],
        "remboursement_id": document["remboursement_id"],
        "variable": document["variable"],
        "valeur": document["valeur"],
    }
    valeurs_set = {
        cle: valeur
        for cle, valeur in document.items()
        if cle not in {
            "remboursement_id",
            "variable",
            "valeur",
            "created_at",
            "statut_verification",
            "label_statut_verification",
            "commentaire",
            "traite_par",
            "traite_le",
            "detecte_le",
        }
    }
    valeurs_set["updated_at"] = datetime.now(timezone.utc)

    resultat = await db[COLLECTION_ANOMALIES].find_one_and_update(
        filtres,
        {
            "$set": valeurs_set,
            "$setOnInsert": {
                "statut_verification": document["statut_verification"],
                "label_statut_verification": document["label_statut_verification"],
                "commentaire": None,
                "traite_par": None,
                "traite_le": None,
                "detecte_le": document["detecte_le"],
                "created_at": document["created_at"],
            },
        },
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    if resultat is not None:
        return resultat.get("_id")
    retrouve = await db[COLLECTION_ANOMALIES].find_one(filtres)
    return retrouve.get("_id") if retrouve else None


async def _assurer_indexes() -> None:
    """Crée les index de la collection (best-effort, non bloquant)."""
    db = obtenir_database()
    collection = db[COLLECTION_ANOMALIES]
    indexages = [
        [("exercice", 1), ("statut_verification", 1)],
        [("exercice", 1), ("niveau", 1)],
        [("exercice", 1), ("variable", 1)],
        [("remboursement_id", 1)],
    ]
    for indexage in indexages:
        try:
            await collection.create_index(indexage)
        except Exception as erreur:  # noqa: BLE001 — environnement contraint (ex. volume Mongo plein)
            logger.warning(
                "Index %s non créé sur %s (la détection reste fonctionnelle) : %s",
                indexage,
                COLLECTION_ANOMALIES,
                erreur,
            )


async def _comptes_anomalies(filtres: list[dict[str, Any]]) -> dict[str, Any]:
    db = obtenir_database()
    base = [{"$match": {"$and": filtres}}] if filtres else []

    par_statut: dict[str, int] = {cle: 0 for cle in STATUTS_VERIFICATION}
    cursor = db[COLLECTION_ANOMALIES].aggregate([
        *base,
        {"$group": {"_id": "$statut_verification", "total": {"$sum": 1}}},
    ])
    async for doc in cursor:
        par_statut[doc["_id"]] = int(doc["total"])

    par_niveau: dict[str, int] = {cle: 0 for cle in NIVEAUX}
    cursor = db[COLLECTION_ANOMALIES].aggregate([
        *base,
        {"$group": {"_id": "$niveau", "total": {"$sum": 1}}},
    ])
    async for doc in cursor:
        par_niveau[doc["_id"]] = int(doc["total"])

    par_methode: dict[str, int] = {cle: 0 for cle in METHODES}
    cursor = db[COLLECTION_ANOMALIES].aggregate([
        *base,
        {"$unwind": "$methodes_detectees"},
        {"$group": {"_id": "$methodes_detectees", "total": {"$sum": 1}}},
    ])
    async for doc in cursor:
        if doc["_id"] in par_methode:
            par_methode[doc["_id"]] = int(doc["total"])

    return {
        "total": int(sum(par_statut.values())),
        "par_statut": par_statut,
        "par_niveau": par_niveau,
        "par_methode": par_methode,
    }


async def detecter_anomalies(
    exercice: Optional[int] = None,
    variables: Optional[list[str]] = None,
    methodes: Optional[list[str]] = None,
    parametres: Optional[dict[str, Any]] = None,
    stocker: bool = True,
) -> dict[str, Any]:
    """Analyse les observations d'un exercice et renvoie les alertes."""
    if exercice is None:
        disponibles = await exercices_remboursements()
        exercice = disponibles[0] if disponibles else datetime.now(timezone.utc).year
    exercice = int(exercice)

    lignes = await _charger_observations(exercice)
    variables_choisies = (
        [v for v in variables if v in VARIABLES_ANALYSABLES]
        if variables
        else list(VARIABLES_ANALYSABLES)
    )

    if stocker:
        await _assurer_indexes()

    run_id = ObjectId()
    calcule_le = datetime.now(timezone.utc)
    variables_resultats: dict[str, dict[str, Any]] = {}
    toutes_anomalies: list[dict[str, Any]] = []
    total_observations = len(lignes)
    total_detectees = 0
    par_methode: dict[str, int] = {cle: 0 for cle in METHODES}
    par_niveau: dict[str, int] = {cle: 0 for cle in NIVEAUX}

    for variable in variables_choisies:
        valeurs = [ligne.get(variable) for ligne in lignes]
        resultat = analyser_variable(
            valeurs,
            lignes,
            methodes=methodes,
            parametres=parametres,
            libelle_variable=VARIABLES_ANALYSABLES[variable]["label"],
        )

        methodes_variable: dict[str, dict[str, Any]] = {}
        for methode in METHODES:
            rapport = resultat["rapports"].get(methode)
            if rapport is None:
                continue
            detectees = sum(
                1 for r in rapport.get("resultats", []) if r["detectee"]
            )
            methodes_variable[methode] = {
                "appliquee": bool(rapport["appliquee"]),
                "raison": rapport["raison"],
                "detectees": detectees,
                "donnees": rapport["donnees"],
            }

        anomalies_variable: list[dict[str, Any]] = []
        for anomalie in resultat["anomalies"]:
            observation = lignes[anomalie["indice"]]
            document = _construire_document_anomalie(
                observation,
                variable,
                anomalie,
                exercice,
                run_id,
                calcule_le,
            )
            if stocker:
                document["_id"] = await _upsert_anomalie(document)
            anomalies_variable.append(_serialiser_anomalie(document))
            for methode in anomalie["methodes_detectees"]:
                par_methode[methode] += 1
            par_niveau[anomalie["niveau"]] += 1
            total_detectees += 1

        variables_resultats[variable] = {
            "label": VARIABLES_ANALYSABLES[variable]["label"],
            "type": VARIABLES_ANALYSABLES[variable]["type"],
            "observations": resultat["observations"],
            "analysable": resultat["analysable"],
            "raison": resultat["raison"],
            "methodes": methodes_variable,
            "anomalies": len(anomalies_variable),
        }
        toutes_anomalies.extend(anomalies_variable)

    comptes = await _comptes_anomalies(
        [{"exercice": exercice}] if stocker else []
    ) if stocker else {
        "total": total_detectees,
        "par_statut": {"a_verifier": total_detectees},
        "par_niveau": par_niveau,
        "par_methode": par_methode,
    }

    return {
        "exercice": exercice,
        "run_id": str(run_id),
        "calcule_le": calcule_le.isoformat(),
        "stocker": stocker,
        "total_observations": total_observations,
        "total_detectees": total_detectees,
        "variables_analysees": variables_resultats,
        "methodes": [
            {
                "cle": methode,
                "label": LABELS_METHODES[methode],
                "detectees": par_methode[methode],
                "minimum_observations": MINIMUM_OBSERVATIONS[methode],
            }
            for methode in METHODES
        ],
        "synthese": {
            "par_methode": par_methode,
            "par_niveau": par_niveau,
            "par_statut": comptes["par_statut"],
        },
        "anomalies": toutes_anomalies,
    }


async def lister_anomalies(
    exercice: Optional[int] = None,
    statut_verification: Optional[str] = None,
    niveau: Optional[str] = None,
    methode: Optional[str] = None,
    variable: Optional[str] = None,
    recherche: Optional[str] = None,
    tri: str = "detecte_le",
    ordre: str = "desc",
    limite: int = 25,
    saut: int = 0,
) -> dict[str, Any]:
    """Liste filtrable et paginée des alertes (les filtres ne suppriment rien)."""
    db = obtenir_database()
    filtres: list[dict[str, Any]] = []
    if exercice is not None:
        filtres.append({"exercice": int(exercice)})
    if statut_verification:
        if statut_verification not in STATUTS_VERIFICATION:
            raise ErreurValidation(
                f"Statut de vérification inconnu : '{statut_verification}'."
            )
        filtres.append({"statut_verification": statut_verification})
    if niveau:
        if niveau not in NIVEAUX:
            raise ErreurValidation(f"Niveau inconnu : '{niveau}'.")
        filtres.append({"niveau": niveau})
    if methode:
        if methode not in METHODES:
            raise ErreurValidation(f"Méthode inconnue : '{methode}'.")
        filtres.append({"methodes_detectees": methode})
    if variable:
        if variable not in VARIABLES_ANALYSABLES:
            raise ErreurValidation(f"Variable inconnue : '{variable}'.")
        filtres.append({"variable": variable})

    if recherche:
        norme = re.compile(re.escape(recherche.strip()), re.IGNORECASE)
        filtres.append({
            "$or": [
                {"numero_dossier": norme},
                {"beneficiaire.nom": norme},
                {"beneficiaire.prenom": norme},
                {"beneficiaire.matricule": norme},
                {"libelle_variable": norme},
                {"justification": norme},
            ]
        })

    if tri not in TRI_VALEURS:
        tri = "detecte_le"
    if ordre not in ("asc", "desc"):
        ordre = "desc"

    total = await db[COLLECTION_ANOMALIES].count_documents(
        {"$and": filtres} if filtres else {}
    )
    comptes = await _comptes_anomalies(filtres)

    curseur = db[COLLECTION_ANOMALIES].find(
        {"$and": filtres} if filtres else {}
    ).sort(tri, -1 if ordre == "desc" else 1).skip(saut).limit(limite)

    items = [
        _serialiser_anomalie(document)
        for document in await curseur.to_list(length=limite)
    ]

    return {
        "total": total,
        "limite": limite,
        "saut": saut,
        "comptes": comptes,
        "items": items,
    }


async def recuperer_anomalie(anomalie_id: str) -> dict[str, Any]:
    """Détail d'une alerte par identifiant ObjectId."""
    try:
        identifiant = ObjectId(anomalie_id)
    except Exception:
        raise ErreurNotFound("Alerte introuvable (identifiant invalide).")
    db = obtenir_database()
    document = await db[COLLECTION_ANOMALIES].find_one({"_id": identifiant})
    if document is None:
        raise ErreurNotFound("Alerte introuvable.")
    return _serialiser_anomalie(document)


async def mettre_a_jour_verification(
    anomalie_id: str,
    statut_verification: str,
    commentaire: Optional[str],
    utilisateur: dict,
) -> dict[str, Any]:
    """Met à jour le statut de vérification (traçabilité utilisateur)."""
    if statut_verification not in STATUTS_VERIFICATION:
        raise ErreurValidation(
            f"Statut de vérification inconnu : '{statut_verification}'. "
            f"Valeurs possibles : {', '.join(STATUTS_VERIFICATION)}."
        )
    try:
        identifiant = ObjectId(anomalie_id)
    except Exception:
        raise ErreurNotFound("Alerte introuvable (identifiant invalide).")

    db = obtenir_database()
    document = await db[COLLECTION_ANOMALIES].find_one({"_id": identifiant})
    if document is None:
        raise ErreurNotFound("Alerte introuvable.")

    maintenant = datetime.now(timezone.utc)
    document = await db[COLLECTION_ANOMALIES].find_one_and_update(
        {"_id": identifiant},
        {
            "$set": {
                "statut_verification": statut_verification,
                "label_statut_verification": STATUTS_VERIFICATION[statut_verification]["label"],
                "commentaire": (commentaire or "").strip() or None,
                "traite_par": utilisateur.get("_id"),
                "traite_le": maintenant,
                "updated_at": maintenant,
            }
        },
        return_document=ReturnDocument.AFTER,
    )
    return _serialiser_anomalie(document)


def referentiel_anomalies() -> dict[str, Any]:
    """Référentiel pour l'interface (méthodes, variables, niveaux, statuts)."""
    return {
        "methodes": [
            {
                "cle": cle,
                "label": LABELS_METHODES[cle],
                "minimum_observations": MINIMUM_OBSERVATIONS[cle],
                "parametres": {
                    cle: value for cle, value in PARAMETRES_PAR_DEFAUT[cle].items()
                },
            }
            for cle in METHODES
        ],
        "variables": [
            {
                "cle": cle,
                "label": infos["label"],
                "type": infos["type"],
            }
            for cle, infos in VARIABLES_ANALYSABLES.items()
        ],
        "niveaux": [
            {
                "cle": cle,
                "label": LABELS_NIVEAUX[cle],
                "description": (
                    "Signalé par 1 méthode indépendante.",
                    "Signalé par 2 méthodes indépendantes.",
                    "Signalé par 3 méthodes indépendantes ou plus.",
                )[index],
            }
            for index, cle in enumerate(NIVEAUX)
        ],
        "statuts_verification": [
            {
                "cle": cle,
                "label": infos["label"],
                "ordre": infos["ordre"],
            }
            for cle, infos in STATUTS_VERIFICATION.items()
        ],
    }