"""Déversement des lignes validées vers les collections métier.

Étape optionnelle de l'importation : prend les lignes normalisées d'une feuille
et les insère (ou met à jour) dans la collection métier correspondante.

Garanties :

- **Idempotence** — l'écriture se fait par clé naturelle (`UpdateOne` +
  `upsert`). Réimporter un même classeur remplace les documents, il n'y a
  jamais de doublon.
- **Persistance** — les documents sont écrits dans les collections métier où
  les services les lisent directement ; ils survivent à la session et à
  l'importation.
- **Références résolues** — `budget_id` et `beneficiaire_id` sont produits par
  interrogation des collections déjà déversées, jamais depuis le classeur.
  Une référence introuvable rejette la ligne avec un motif explicite plutôt
  que d'écrire un document orphelin.
- **Staging intact** — `importations_nettoyees` conserve les valeurs du
  classeur, enrichies des identifiants résolus.

L'ordre des cibles (déclaré dans `app.imports.cibles`) impose le traitement :
bénéficiaires → budgets → exécutions → remboursements.
"""

from __future__ import annotations

from typing import Any

from bson import ObjectId
from pymongo import ASCENDING, UpdateOne

from app.database import obtenir_database
from app.imports.cibles import CibleImportation, appliquer_alias, construire_document
from app.imports.stockage import bsoniser_valeurs
from app.utils.logging import get_logger

logger = get_logger(__name__)

LOT = 500

INDEXES: dict[str, tuple[list[tuple[str, int]], bool]] = {
    "beneficiaires": ([("matricule", ASCENDING)], True),
    "budgets_rfm": ([("exercice", 1), ("chapitre", 1),
                     ("ligne_budgetaire", 1), ("nature", 1)], True),
    "executions": ([("budget_id", 1), ("mois", 1), ("phase", 1)], True),
    "remboursements": ([("numero_dossier", ASCENDING)], True),
}


async def preparer_collection(cible: CibleImportation) -> None:
    """Crée l'index de clé naturelle (idempotent). Un échec n'arrête pas l'import."""
    indices = INDEXES.get(cible.cle)
    if not indices:
        return
    try:
        await obtenir_database()[cible.collection].create_index(
            indices[0], unique=indices[1]
        )
    except Exception as erreur:  # noqa: BLE001
        logger.warning(
            "Index de '%s' non créé (%s) : la clé de filtre reste appliquée.",
            cible.collection,
            erreur,
        )


def _rejet(ligne: int, colonne: str, valeur: Any, raison: str) -> dict:
    return {
        "ligne": ligne,
        "colonne": colonne,
        "valeur": "" if valeur is None else str(valeur),
        "raison": raison,
        "type_erreur": "deversement",
    }


async def _index_reference(
    type_reference: str,
    cles: set[tuple],
) -> dict[tuple, ObjectId]:
    """Mappe une clé naturelle (tuple) vers l'`_id` de la collection cible."""
    if not cles:
        return {}

    db = obtenir_database()
    resolu: dict[tuple, ObjectId] = {}

    if type_reference == "budget":
        exercices = sorted({cle[0] for cle in cles if isinstance(cle[0], int)})
        curseur = db["budgets_rfm"].find(
            {"exercice": {"$in": exercices}},
            {"exercice": 1, "ligne_budgetaire": 1, "nature": 1},
        )
        async for doc in curseur:
            resolu[(
                doc.get("exercice"),
                doc.get("ligne_budgetaire"),
                doc.get("nature"),
            )] = doc["_id"]
        return resolu

    if type_reference == "beneficiaire":
        matricules = sorted({cle[0] for cle in cles if cle[0]})
        for depart in range(0, len(matricules), 1000):
            curseur = db["beneficiaires"].find(
                {"matricule": {"$in": matricules[depart:depart + 1000]}},
                {"matricule": 1},
            )
            async for doc in curseur:
                resolu[(doc["matricule"],)] = doc["_id"]
        return resolu

    raise ValueError(f"Type de référence inconnu : {type_reference}")


async def deverser(
    cible: CibleImportation,
    lignes: list[Any],
) -> tuple[dict, list[dict]]:
    """Déverse des lignes validées vers la collection métier.

    Renvoie `(rapport, rejets)` — les rejets sont à verser dans ceux du
    pipeline (`importations_rejets`).
    """
    await preparer_collection(cible)
    collection = obtenir_database()[cible.collection]

    rejets: list[dict] = []
    retenues: dict[int, dict] = {}

    champs_reference = {ref.champ for ref in cible.references}
    colonnes_reference = {c for ref in cible.references for c in ref.colonnes}

    for ligne in lignes:
        valeurs = appliquer_alias(cible, dict(ligne.valeurs or {}))

        cles_absentes = [
            c for c in cible.cles
            if c not in champs_reference and valeurs.get(c) in (None, "")
        ]
        if cles_absentes:
            rejets.append(_rejet(
                ligne.numero, cles_absentes[0], valeurs.get(cles_absentes[0]),
                f"Clé de déversement absente ({', '.join(cles_absentes)})",
            ))
            continue

        hors_referentiel = None
        for champ, autorisees in cible.enums.items():
            brut = valeurs.get(champ)
            if brut is None:
                continue
            texte = str(brut).strip().lower()
            if texte not in autorisees:
                hors_referentiel = (champ, brut, autorisees)
                break
            valeurs[champ] = texte
        if hors_referentiel:
            champ, brut, autorisees = hors_referentiel
            rejets.append(_rejet(
                ligne.numero, champ, brut,
                f"Valeur hors référentiel ({champ}) : attendu "
                f"{' | '.join(autorisees)}",
            ))
            continue

        incomplete = False
        for ref in cible.references:
            manquantes = [c for c in ref.colonnes if valeurs.get(c) in (None, "")]
            if manquantes:
                rejets.append(_rejet(
                    ligne.numero, manquantes[0], valeurs.get(manquantes[0]),
                    f"Référence {ref.type} incomplète "
                    f"({', '.join(ref.colonnes)} requis)",
                ))
                incomplete = True
        if incomplete:
            continue

        retenues[ligne.numero] = valeurs

    for ref in cible.references:
        besoins = {
            tuple(valeurs.get(c) for c in ref.colonnes)
            for valeurs in retenues.values()
        }
        index = await _index_reference(ref.type, besoins)
        for numero, valeurs in list(retenues.items()):
            cle = tuple(valeurs.get(c) for c in ref.colonnes)
            _id = index.get(cle)
            if _id is None:
                rejets.append(_rejet(
                    numero, ref.colonnes[0], valeurs.get(ref.colonnes[0]),
                    f"Référence {ref.type} introuvable : importez d'abord "
                    f"{'la feuille en amont' if ref.type == 'budget' else 'les bénéficiaires'}",
                ))
                del retenues[numero]
                continue
            valeurs[ref.champ] = _id

    documents: list[dict[str, Any]] = []
    par_numero: dict[int, dict] = {}
    for numero, valeurs in retenues.items():
        document = construire_document(cible, bsoniser_valeurs(valeurs))
        if document:
            par_numero[numero] = document
            documents.append(document)

    insere = 0
    mis_a_jour = 0
    for depart in range(0, len(documents), LOT):
        operations = []
        for document in documents[depart:depart + LOT]:
            filtre = {c: document.get(c) for c in cible.cles}
            mise_a_jour = {
                k: v for k, v in document.items() if k != "created_at"
            }
            operation = {"$set": mise_a_jour}
            if "created_at" in document:
                operation["$setOnInsert"] = {"created_at": document["created_at"]}
            operations.append(UpdateOne(filtre, operation, upsert=True))

        resultat = await collection.bulk_write(operations, ordered=False)
        insere += len(resultat.upserted_ids)
        mis_a_jour += resultat.matched_count

    rapport = {
        "cible": cible.cle,
        "collection": cible.collection,
        "lignes_soumises": len(lignes),
        "lignes_deversees": len(documents),
        "insere": insere,
        "mise_a_jour": mis_a_jour,
        "rejetees": len(rejets),
    }
    if documents or rejets:
        logger.info(
            "Déversement '%s' : %s versées (%s insérées, %s mises à jour), "
            "%s rejetées",
            cible.collection, len(documents), insere, mis_a_jour, len(rejets),
        )
    return rapport, rejets
