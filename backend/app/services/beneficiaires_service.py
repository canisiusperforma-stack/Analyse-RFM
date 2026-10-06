"""Indicateurs et liste de la population bénéficiaire (agrégations MongoDB).

Le service alimente la page « Bénéficiaires » : statistiques, filtres,
tableau paginé et comparaisons. Deux sources de données sont prises en
charge, de façon transparente pour le frontend :

- `metier` : collections `beneficiaires` (+ `remboursements` pour le statut
  RFM) — source privilégiée quand elle contient des données ;
- `importation` : lignes normalisées de `importations_nettoyees` (champs
  portés par `valeurs`, colonnes snake_case ascii) — repli lorsque les
  collections métier sont vides.

Le champ `source` de chaque réponse indique la source effective. Aucune
valeur d'indicateur n'est écrite en dur côté frontend.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Optional

from app.database import obtenir_database
from app.services.dashboard_service import (
    COLLECTION_BENEFICIAIRES,
    COLLECTION_REMBOURSEMENTS,
    _entete,
)

COLLECTION_IMPORTS_NETTOYEES = "importations_nettoyees"

SOURCE_METIER = "metier"
SOURCE_IMPORTATION = "importation"

# Champs portés par importations_nettoyees pour une importation de type
# « bénéficiaires » (noms normalisés snake_case par le pipeline d'import).
PROJECTION_IMPORTS: dict[str, Any] = {
    "id_originale": "$_id",
    "matricule": "$valeurs.matricule",
    "nom": "$valeurs.nom",
    "prenom": "$valeurs.prenom",
    "date_naissance": "$valeurs.date_de_naissance",
    "situation": "$valeurs.situation",
    "categorie": "$valeurs.categorie",
    "genre": "$valeurs.genre",
    "direction": "$valeurs.direction",
    "exercice": "$valeurs.exercice",
}

PROJECTION_METIER: dict[str, Any] = {
    "id_originale": "$_id",
    "matricule": "$matricule",
    "nom": "$nom",
    "prenom": "$prenom",
    "date_naissance": "$date_naissance",
    "situation": "$situation",
    "categorie": "$categorie",
    "genre": "$genre",
    "direction": "$direction",
    "exercice": None,
    "statut_dossier": "$statut_dossier",
    "created_at": "$created_at",
}

TYPES_AGE = (
    ("moins_de_30", "< 30 ans", lambda a: a < 30),
    ("30_a_39", "30-39 ans", lambda a: 30 <= a < 40),
    ("40_a_49", "40-49 ans", lambda a: 40 <= a < 50),
    ("50_a_59", "50-59 ans", lambda a: 50 <= a < 60),
    ("60_et_plus", "60 ans et +", lambda a: a >= 60),
)

# Libellés lisibles des situations, pour les réponses de l'assistant.
LIBELLES_SITUATION: dict[str, str] = {
    "actif": "actifs",
    "pensionne": "pensionnés",
    "indeterminee": "situation indéterminée",
}


async def _source_active() -> str:
    """Renvoie la source effective (métier, sinon importation)."""
    db = obtenir_database()
    if await db[COLLECTION_BENEFICIAIRES].count_documents({}) > 0:
        return SOURCE_METIER
    nb_imports = await db[COLLECTION_IMPORTS_NETTOYEES].count_documents(
        {"valeurs.matricule": {"$exists": True}}
    )
    if nb_imports > 0:
        return SOURCE_IMPORTATION
    return SOURCE_METIER


def _chemin(source: str, champ: str) -> str:
    """Chemin MongoDB d'un champ population selon la source."""
    if source == SOURCE_IMPORTATION:
        return f"valeurs.{champ}"
    return champ


def _collection(source: str) -> str:
    return COLLECTION_BENEFICIAIRES if source == SOURCE_METIER else COLLECTION_IMPORTS_NETTOYEES


def _projeter(source: str) -> dict[str, Any]:
    return PROJECTION_IMPORTS if source == SOURCE_IMPORTATION else PROJECTION_METIER


def _age_a_fin_exercice(date_naissance: Any, exercice: int) -> Optional[float]:
    if date_naissance is None:
        return None
    if isinstance(date_naissance, datetime):
        naissance = date_naissance
    elif isinstance(date_naissance, str):
        try:
            naissance = datetime.fromisoformat(date_naissance.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    fin = datetime(exercice + 1, 1, 1, tzinfo=timezone.utc)
    jours = (fin - naissance).days
    return jours / 365.25 if jours >= 0 else None


def _tranche_age(age: Optional[float]) -> Optional[str]:
    if age is None:
        return None
    for cle, _, condition in TYPES_AGE:
        if condition(age):
            return cle
    return None


def _filtre_periode(source: str, exercice: int) -> dict[str, Any]:
    """Recensement selon la source : année d'exercice (import) ou recensé à fin (métier)."""
    if source == SOURCE_IMPORTATION:
        return {"valeurs.exercice": int(exercice)}
    _, fin = _entete(exercice)
    return {"created_at": {"$lte": fin}}


def _filtres_communs(
    source: str,
    *,
    exercice: int,
    recherche: Optional[str] = None,
    situation: Optional[str] = None,
    categorie: Optional[str] = None,
    genre: Optional[str] = None,
    direction: Optional[str] = None,
    statut_dossier: Optional[str] = None,
) -> list[dict[str, Any]]:
    chemin = _chemin(source, "{champ}")
    pipeline: list[dict[str, Any]] = [
        {"$match": _filtre_periode(source, exercice)},
        {"$match": {chemin.format(champ="matricule"): {"$exists": True, "$ne": None}}},
    ]
    if recherche and recherche.strip():
        motif = re.escape(recherche.strip())
        pipeline.append({
            "$match": {
                "$or": [
                    {chemin.format(champ=c): {"$regex": motif, "$options": "i"}}
                    for c in ("matricule", "nom", "prenom")
                ]
            }
        })
    for champ, valeur in (
        ("situation", situation),
        ("categorie", categorie),
        ("genre", genre),
        ("direction", direction),
        ("statut_dossier", statut_dossier),
    ):
        if valeur:
            pipeline.append({"$match": {chemin.format(champ=champ): valeur}})
    return pipeline


async def _projeter_population(exercice: int, source: str) -> list[dict[str, Any]]:
    """Docs projetés (champs communs) de la population recensée de l'exercice."""
    db = obtenir_database()
    pipeline: list[dict[str, Any]] = [
        {"$match": _filtre_periode(source, exercice)},
        {
            "$match": {
                _chemin(source, "matricule"): {"$exists": True, "$ne": None}
            }
        },
        {"$project": _projeter(source)},
    ]
    documents: list[dict[str, Any]] = []
    cursor = db[_collection(source)].aggregate(pipeline)
    async for doc in cursor:
        documents.append(doc)
    return documents


async def _identifiants_rfm(exercice: int) -> set[str]:
    """Ids (string) des bénéficiaires ayant au moins une demande dans l'exercice."""
    db = obtenir_database()
    debut, fin = _entete(exercice)
    identifiants: set[str] = set()
    cursor = db[COLLECTION_REMBOURSEMENTS].aggregate([
        {"$match": {"date_demande": {"$gte": debut, "$lt": fin}}},
        {"$group": {"_id": "$beneficiaire_id"}},
    ])
    async for doc in cursor:
        identifiants.add(str(doc["_id"]))
    return identifiants


async def exercices_population() -> list[int]:
    """Exercices disponibles pour la population (source effective), décroissant."""
    db = obtenir_database()
    source = await _source_active()
    exercices: set[int] = set()

    if source == SOURCE_METIER:
        cursor = db[COLLECTION_BENEFICIAIRES].aggregate([
            {"$group": {"_id": {"$year": "$created_at"}}}
        ])
        async for doc in cursor:
            exercices.add(int(doc["_id"]))
        cursor = db[COLLECTION_REMBOURSEMENTS].aggregate([
            {"$group": {"_id": {"$year": "$date_demande"}}}
        ])
        async for doc in cursor:
            exercices.add(int(doc["_id"]))
    else:
        cursor = db[COLLECTION_IMPORTS_NETTOYEES].aggregate([
            {"$match": {"valeurs.matricule": {"$exists": True}}},
            {"$group": {"_id": "$valeurs.exercice"}},
        ])
        async for doc in cursor:
            if doc["_id"] is not None:
                exercices.add(int(doc["_id"]))

    if not exercices:
        return []
    return sorted(exercices, reverse=True)


def _resoudre_exercice(exercices_disponibles: list[int]) -> int:
    if exercices_disponibles:
        return exercices_disponibles[0]
    return datetime.now(timezone.utc).year


async def _statistiques_spécifiques(
    documents: list[dict[str, Any]],
    exercice: int,
    rfm_ids: set[str],
) -> dict[str, Any]:
    actifs = 0
    pensionnes = 0
    indetermines = 0
    par_situation: dict[str, int] = {}
    par_categorie: dict[str, int] = {}
    par_genre: dict[str, int] = {}
    par_direction: dict[str, int] = {}
    par_tranche: dict[str, int] = {}
    ages: list[float] = []
    beneficiaires_rfm = 0

    for document in documents:
        situation = (document.get("situation") or "indeterminee").strip().lower() or "indeterminee"
        if situation == "actif":
            actifs += 1
        elif situation == "pensionne":
            pensionnes += 1
        else:
            indetermines += 1
        par_situation[situation] = par_situation.get(situation, 0) + 1
        categorie = document.get("categorie") or "inconnue"
        genre = document.get("genre") or "inconnu"
        direction = document.get("direction") or "Non renseignée"
        par_categorie[categorie] = par_categorie.get(categorie, 0) + 1
        par_genre[genre] = par_genre.get(genre, 0) + 1
        par_direction[direction] = par_direction.get(direction, 0) + 1

        age = _age_a_fin_exercice(document.get("date_naissance"), exercice)
        if age is not None:
            ages.append(age)
            tranche = _tranche_age(age)
            if tranche:
                par_tranche[tranche] = par_tranche.get(tranche, 0) + 1

        if str(document.get("id_originale")) in rfm_ids:
            beneficiaires_rfm += 1

    total = len(documents)
    return {
        "total": total,
        "actifs": actifs,
        "pensionnes": pensionnes,
        "indetermines": indetermines,
        "taux_dactifs": round(actifs / total, 4) if total else 0.0,
        "beneficiaires_rfm": beneficiaires_rfm,
        "taux_demarche_rfm": round(beneficiaires_rfm / total, 4) if total else 0.0,
        "moyenne_age": round(sum(ages) / len(ages), 1) if ages else None,
        "age_minimal": round(min(ages)) if ages else None,
        "age_maximal": round(max(ages)) if ages else None,
        "repartition_par_situation": [
            {"situation": situation, "total": total_valeur}
            for situation, total_valeur in sorted(par_situation.items(), key=lambda item: item[1], reverse=True)
        ],
        "repartition_par_categorie": [
            {"categorie": categorie, "total": total_valeur}
            for categorie, total_valeur in sorted(par_categorie.items(), key=lambda item: item[1], reverse=True)
        ],
        "repartition_par_genre": [
            {"genre": genre, "total": total_valeur}
            for genre, total_valeur in sorted(par_genre.items(), key=lambda item: item[1], reverse=True)
        ],
        "repartition_par_direction": [
            {"direction": direction, "total": total_valeur}
            for direction, total_valeur in sorted(par_direction.items(), key=lambda item: item[1], reverse=True)[:5]
        ],
        "tranches_age": [
            {"tranche": cle, "libelle": libelle, "total": par_tranche.get(cle, 0)}
            for cle, libelle, _ in TYPES_AGE
        ],
    }


async def statistiques_population(exercice: Optional[int] = None) -> dict[str, Any]:
    """Statistiques de la population d'un exercice, avec comparaison au précédent."""
    source = await _source_active()
    exercices_disponibles = await exercices_population()
    exercice = int(exercice) if exercice is not None else _resoudre_exercice(exercices_disponibles)

    rfm_ids = await _identifiants_rfm(exercice) if source == SOURCE_METIER else set()
    documents = await _projeter_population(exercice, source)
    specifiques = await _statistiques_spécifiques(documents, exercice, rfm_ids)

    comparaison = await _comparaison(source, exercice, rfm_ids, specifiques)

    return {
        "exercice": exercice,
        "source": source,
        **specifiques,
        "comparaison": comparaison,
    }


async def croisement_situation_rfm(exercice: Optional[int] = None) -> dict[str, Any]:
    """Croisement situation (actif / pensionné) × statut RFM d'un exercice.

    `statistiques_population` donne les effectifs de chaque dimension
    séparément (actifs, pensionnés, bénéficiaires RFM) mais jamais leur
    intersection, qui répond pourtant à des questions centrales du RFM
    (« combien de pensionnés ont bénéficié du RFM ? »). Ce croisement est donc
    calculé ici, à partir des mêmes projections que les autres indicateurs.

    Le statut RFM est déduit des demandes de remboursement rattachées au
    bénéficiaire (`_identifiants_rfm`). Il n'est donc déterminable que si la
    source active porte la collection métier : pour une population reconstituée
    par importation, aucun rattachement n'existe. Le retour expose alors
    `disponible = False` et un motif, afin que l'appelant déclare l'information
    absente au lieu d'annoncer un faux zéro.
    """
    source = await _source_active()
    exercices_disponibles = await exercices_population()
    exercice = int(exercice) if exercice is not None else _resoudre_exercice(exercices_disponibles)

    documents = await _projeter_population(exercice, source)

    if source != SOURCE_METIER:
        return {
            "exercice": exercice,
            "source": source,
            "disponible": False,
            "motif": (
                "Le statut RFM est déduit des demandes de remboursement "
                "rattachées au bénéficiaire ; or la population provient d'une "
                "importation, sans ces rattachements. Le croisement "
                "situation / RFM n'est donc pas calculable sur cette source."
            ),
            "croisement": [],
            "total": len(documents),
        }

    rfm_ids = await _identifiants_rfm(exercice)

    croisement: dict[str, dict[str, int]] = {}
    for document in documents:
        situation = (
            (document.get("situation") or "indeterminee").strip().lower()
            or "indeterminee"
        )
        rfm = "oui" if str(document.get("id_originale")) in rfm_ids else "non"
        ligne = croisement.setdefault(
            situation, {"rfm": 0, "non_rfm": 0, "total": 0}
        )
        ligne["rfm" if rfm == "oui" else "non_rfm"] += 1
        ligne["total"] += 1

    lignes = [
        {
            "situation": situation,
            "situation_libelle": LIBELLES_SITUATION.get(situation, situation),
            "rfm": valeurs["rfm"],
            "non_rfm": valeurs["non_rfm"],
            "total": valeurs["total"],
            "taux_rfm": round(valeurs["rfm"] / valeurs["total"], 4)
            if valeurs["total"]
            else 0.0,
        }
        for situation, valeurs in sorted(
            croisement.items(), key=lambda item: item[1]["total"], reverse=True
        )
    ]

    return {
        "exercice": exercice,
        "source": source,
        "disponible": True,
        "motif": None,
        "croisement": lignes,
        "total": len(documents),
    }


async def _comparaison(
    source: str,
    exercice: int,
    rfm_ids: set[str],
    specifiques: dict[str, Any],
) -> Optional[dict[str, Any]]:
    """Comparaison population courante vs exercice précédent (si données existantes)."""
    precedent = exercice - 1
    documents_precedents = await _projeter_population(precedent, source)
    if not documents_precedents:
        return None

    rfm_ids_precedent = await _identifiants_rfm(precedent) if source == SOURCE_METIER else set()
    specifiques_precedents = await _statistiques_spécifiques(
        documents_precedents, precedent, rfm_ids_precedent
    )

    def _ecart(courant: float | int, precedent_valeur: float | int) -> float:
        return round(float(courant) - float(precedent_valeur), 1)

    return {
        "exercice_precedent": precedent,
        "total": specifiques["total"],
        "actifs": specifiques["actifs"],
        "pensionnes": specifiques["pensionnes"],
        "beneficiaires_rfm": specifiques["beneficiaires_rfm"],
        "ecart_total": _ecart(specifiques["total"], specifiques_precedents["total"]),
        "ecart_actifs": _ecart(specifiques["actifs"], specifiques_precedents["actifs"]),
        "ecart_pensionnes": _ecart(specifiques["pensionnes"], specifiques_precedents["pensionnes"]),
        "ecart_rfm": _ecart(
            specifiques["beneficiaires_rfm"], specifiques_precedents["beneficiaires_rfm"]
        ),
    }


def _construire_item(
    document: dict[str, Any],
    rfm_ids: Optional[set[str]],
    exercice: int,
) -> dict[str, Any]:
    age = _age_a_fin_exercice(document.get("date_naissance"), exercice)
    item: dict[str, Any] = {
        "id": str(document["id_originale"]) if document.get("id_originale") else None,
        "matricule": document.get("matricule"),
        "nom": document.get("nom"),
        "prenom": document.get("prenom"),
        "date_naissance": (
            document["date_naissance"].isoformat()
            if isinstance(document.get("date_naissance"), datetime)
            else document.get("date_naissance")
        ),
        "age": round(age) if age is not None else None,
        "tranche_age": _tranche_age(age),
        "situation": (document.get("situation") or "indeterminee").strip().lower() or "indeterminee",
        "categorie": document.get("categorie") or "inconnue",
        "genre": document.get("genre") or "inconnu",
        "direction": document.get("direction") or "Non renseignée",
        "exercice": document.get("exercice"),
        "statut_dossier": document.get("statut_dossier"),
    }
    if rfm_ids is not None:
        item["rfm"] = "oui" if str(document.get("id_originale")) in rfm_ids else "non"
    return item


def _cle_tri(item: dict[str, Any], tri: str, ordre: str):
    if tri == "age":
        valeur_entier = item.get("age")
        if valeur_entier is None:
            return (1, 0)
        return (0, int(valeur_entier))
    valeur = item.get(tri)
    if valeur is None:
        return (1, "")
    return (0, str(valeur).casefold())


async def lister_beneficiaires(
    *,
    exercice: Optional[int] = None,
    recherche: Optional[str] = None,
    situation: Optional[str] = None,
    categorie: Optional[str] = None,
    genre: Optional[str] = None,
    direction: Optional[str] = None,
    statut_dossier: Optional[str] = None,
    rfm: Optional[str] = None,
    tri: str = "nom",
    ordre: str = "asc",
    limite: int = 50,
    saut: int = 0,
) -> dict[str, Any]:
    """Liste paginée et filtrable de la population recensée."""
    source = await _source_active()
    exercices_disponibles = await exercices_population()
    exercice = int(exercice) if exercice is not None else _resoudre_exercice(exercices_disponibles)

    pipeline = _filtres_communs(
        source,
        exercice=exercice,
        recherche=recherche,
        situation=situation,
        categorie=categorie,
        genre=genre,
        direction=direction,
        statut_dossier=statut_dossier,
    )
    pipeline.append({"$project": _projeter(source)})

    db = obtenir_database()
    documents: list[dict[str, Any]] = []
    cursor = db[_collection(source)].aggregate(pipeline)
    async for doc in cursor:
        documents.append(doc)

    rfm_ids = await _identifiants_rfm(exercice) if source == SOURCE_METIER else None
    items = [_construire_item(doc, rfm_ids, exercice) for doc in documents]

    if rfm in ("oui", "non"):
        items = [item for item in items if item.get("rfm") == rfm]

    items.sort(key=lambda item: _cle_tri(item, tri, ordre), reverse=(ordre == "desc"))

    total = len(items)
    return {
        "exercice": exercice,
        "source": source,
        "total": total,
        "saut": max(saut, 0),
        "limite": min(max(limite, 1), 200),
        "items": items[saut : saut + limite],
    }