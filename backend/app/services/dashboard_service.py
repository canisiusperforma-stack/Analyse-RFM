"""Calcul des indicateurs du tableau de bord (agrégations MongoDB).

Toute valeur affichée côté frontend provient de ce service : aucun chiffre
n'est écrit en dur dans le frontend. Le service calcule à la volée, par
exercice budgétaire :

- la population des bénéficiaires (recensés à fin d'exercice) ;
- les crédits votés (LFI / LFR) et l'exécution budgétaire par phase
  (engagement, liquidation, ordonnancement, paiement) avec les indicateurs
  dérivés (disponible, solde, taux d'exécution) ;
- les demandes de remboursement (volume, statuts, montants, moyennes) ;
- les séries mensuelles et les répartitions destinées aux graphiques ;
- un résumé analytique construit à partir des valeurs calculées.

Le modèle de données suit la proposition de `docs/modele-donnees.md`
enrichie de deux champs : `budgets_rfm.nature` (lfi | lfr) et
`executions.phase` (engagement | liquidation | ordonnancement | paiement).
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional

from bson import Decimal128

from app.database import obtenir_database

COLLECTION_BENEFICIAIRES = "beneficiaires"
COLLECTION_BUDGETS = "budgets_rfm"
COLLECTION_EXECUTIONS = "executions"
COLLECTION_REMBOURSEMENTS = "remboursements"

NATURE_LFI = "lfi"
NATURE_LFR = "lfr"

PHASES_EXECUTION = ("engagement", "liquidation", "ordonnancement", "paiement")
PHASE_EXECUTION_FINALE = "paiement"

STATUTS_ACCEPTES = ("valide", "paye")
STATUTS_EN_ATTENTE = ("soumis", "a_completer", "en_cours")
STATUT_REFUSE = "refuse"
STATUT_PAYE = "paye"


def _montant(document: dict[str, Any], champ: str) -> float:
    """Renvoie la valeur (Decimal128 | Decimal | int | float | None) en float."""
    valeur = document.get(champ)
    if valeur is None:
        return 0.0
    if isinstance(valeur, Decimal128):
        return float(valeur.to_decimal())
    if isinstance(valeur, Decimal):
        return float(valeur)
    return float(valeur)


def _entete(exercice: int) -> tuple[datetime, datetime]:
    return (
        datetime(exercice, 1, 1, tzinfo=timezone.utc),
        datetime(exercice + 1, 1, 1, tzinfo=timezone.utc),
    )


def _mois_de_lexercice(exercice: int) -> list[str]:
    return [f"{exercice:04d}-{mois:02d}" for mois in range(1, 13)]


async def analyser_exercices() -> list[int]:
    """Exercices disponibles (budgets, puis remboursements), ordre décroissant."""
    db = obtenir_database()
    exercices: set[int] = set()

    cursor = db[COLLECTION_BUDGETS].aggregate([{"$group": {"_id": "$exercice"}}])
    async for doc in cursor:
        exercices.add(int(doc["_id"]))

    cursor = db[COLLECTION_REMBOURSEMENTS].aggregate([
        {"$group": {"_id": {"$year": "$date_demande"}}}
    ])
    async for doc in cursor:
        exercices.add(int(doc["_id"]))

    return sorted(exercices, reverse=True)


async def _population(exercice: int) -> dict[str, Any]:
    db = obtenir_database()
    _, fin = _entete(exercice)
    filtre_periode = {"created_at": {"$lte": fin}}

    total = await db[COLLECTION_BENEFICIAIRES].count_documents(filtre_periode)

    actifs = 0
    pensionnes = 0
    repartition_situation: list[dict[str, Any]] = []
    repartition_categorie: list[dict[str, Any]] = []
    if total > 0:
        cursor = db[COLLECTION_BENEFICIAIRES].aggregate([
            {"$match": filtre_periode},
            {"$group": {"_id": "$situation", "total": {"$sum": 1}}},
            {"$sort": {"total": -1}},
        ])
        async for doc in cursor:
            situation = doc["_id"] or "indeterminee"
            repartition_situation.append({"situation": situation, "total": int(doc["total"])})
            if situation == "actif":
                actifs = int(doc["total"])
            elif situation == "pensionne":
                pensionnes = int(doc["total"])

        cursor = db[COLLECTION_BENEFICIAIRES].aggregate([
            {"$match": filtre_periode},
            {"$group": {"_id": "$categorie", "total": {"$sum": 1}}},
            {"$sort": {"total": -1}},
        ])
        async for doc in cursor:
            repartition_categorie.append(
                {"categorie": doc["_id"] or "inconnue", "total": int(doc["total"])}
            )

    debut, fin = _entete(exercice)
    cursor = db[COLLECTION_REMBOURSEMENTS].aggregate([
        {"$match": {"date_demande": {"$gte": debut, "$lt": fin}}},
        {"$group": {"_id": "$beneficiaire_id"}},
        {"$count": "total"},
    ])
    beneficiaires_rfm = 0
    async for doc in cursor:
        beneficiaires_rfm = int(doc["total"])

    return {
        "total": total,
        "actifs": actifs,
        "pensionnes": pensionnes,
        "beneficiaires_rfm": beneficiaires_rfm,
        "repartition_par_situation": repartition_situation,
        "repartition_par_categorie": repartition_categorie,
    }


async def _budget(exercice: int) -> dict[str, Any]:
    db = obtenir_database()

    async def _voter(nature: str) -> float:
        cursor = db[COLLECTION_BUDGETS].aggregate([
            {"$match": {"exercice": exercice, "nature": nature}},
            {"$group": {"_id": None, "total": {"$sum": "$montant_vote"}}},
        ])
        async for doc in cursor:
            return _montant(doc, "total")
        return 0.0

    lfi = await _voter(NATURE_LFI)
    lfr = await _voter(NATURE_LFR)
    credits_ouverts = lfr if lfr > 0 else lfi

    lignes_budgetaires = await db[COLLECTION_BUDGETS].count_documents(
        {"exercice": exercice, "nature": NATURE_LFR}
    ) or await db[COLLECTION_BUDGETS].count_documents(
        {"exercice": exercice, "nature": NATURE_LFI}
    )

    par_phase: dict[str, float] = {phase: 0.0 for phase in PHASES_EXECUTION}
    cursor = db[COLLECTION_EXECUTIONS].aggregate([
        {
            "$lookup": {
                "from": COLLECTION_BUDGETS,
                "localField": "budget_id",
                "foreignField": "_id",
                "as": "budget",
            }
        },
        {"$match": {"budget.exercice": exercice}},
        {"$group": {"_id": "$phase", "total": {"$sum": "$montant"}}},
    ])
    async for doc in cursor:
        phase = doc["_id"]
        if phase in par_phase:
            par_phase[phase] = _montant(doc, "total")

    engage = par_phase["engagement"]
    liquide = par_phase["liquidation"]
    ordonnance = par_phase["ordonnancement"]
    execute = par_phase[PHASE_EXECUTION_FINALE]

    disponible = max(0.0, credits_ouverts - engage)
    solde = credits_ouverts - execute
    taux_execution = execute / credits_ouverts if credits_ouverts > 0 else 0.0

    serie_mensuelle: list[dict[str, Any]] = []
    cursor = db[COLLECTION_EXECUTIONS].aggregate([
        {
            "$lookup": {
                "from": COLLECTION_BUDGETS,
                "localField": "budget_id",
                "foreignField": "_id",
                "as": "budget",
            }
        },
        {"$match": {"budget.exercice": exercice, "phase": PHASE_EXECUTION_FINALE}},
        {"$group": {"_id": "$mois", "montant": {"$sum": "$montant"}}},
        {"$sort": {"_id": 1}},
    ])
    cumul = 0.0
    present: set[str] = set()
    async for doc in cursor:
        mois = doc["_id"]
        present.add(mois)
        cumul += _montant(doc, "montant")
        serie_mensuelle.append({
            "mois": mois,
            "montant": round(_montant(doc, "montant"), 2),
            "cumul": round(cumul, 2),
        })

    for mois in _mois_de_lexercice(exercice):
        if mois not in present:
            serie_mensuelle.append({"mois": mois, "montant": 0.0, "cumul": cumul})
    serie_mensuelle.sort(key=lambda item: item["mois"])

    repartition_par_type: list[dict[str, Any]] = []
    cursor = db[COLLECTION_EXECUTIONS].aggregate([
        {
            "$lookup": {
                "from": COLLECTION_BUDGETS,
                "localField": "budget_id",
                "foreignField": "_id",
                "as": "budget",
            }
        },
        {"$match": {"budget.exercice": exercice, "phase": PHASE_EXECUTION_FINALE}},
        {
            "$group": {
                "_id": {"$arrayElemAt": ["$budget.type", 0]},
                "montant": {"$sum": "$montant"},
            }
        },
        {"$sort": {"montant": -1}},
    ])
    async for doc in cursor:
        repartition_par_type.append({
            "type": doc["_id"] or "inconnu",
            "montant": round(_montant(doc, "montant"), 2),
        })

    return {
        "lfi": round(lfi, 2),
        "lfr": round(lfr, 2),
        "credits_ouverts": round(credits_ouverts, 2),
        "engage": round(engage, 2),
        "liquide": round(liquide, 2),
        "ordonnance": round(ordonnance, 2),
        "execute": round(execute, 2),
        "disponible": round(disponible, 2),
        "solde": round(solde, 2),
        "taux_execution": round(taux_execution, 6),
        "lignes_budgetaires": int(lignes_budgetaires),
        "execution_mensuelle": serie_mensuelle,
        "repartition_par_type": repartition_par_type,
    }


async def _remboursements(exercice: int) -> dict[str, Any]:
    db = obtenir_database()
    debut, fin = _entete(exercice)
    filtre_periode = {"date_demande": {"$gte": debut, "$lt": fin}}

    demandes = await db[COLLECTION_REMBOURSEMENTS].count_documents(filtre_periode)

    async def _compter_statuts(statuts: tuple[str, ...]) -> int:
        if not statuts:
            return 0
        return await db[COLLECTION_REMBOURSEMENTS].count_documents({
            **filtre_periode,
            "statut": {"$in": list(statuts)},
        })

    acceptees = await _compter_statuts(STATUTS_ACCEPTES)
    rejetees = await _compter_statuts((STATUT_REFUSE,))
    en_attente = await _compter_statuts(STATUTS_EN_ATTENTE)
    payes = await _compter_statuts((STATUT_PAYE,))

    montant_demande = 0.0
    cursor = db[COLLECTION_REMBOURSEMENTS].aggregate([
        {"$match": filtre_periode},
        {"$group": {"_id": None, "total": {"$sum": "$montant_demande"}}},
    ])
    async for doc in cursor:
        montant_demande = _montant(doc, "total")

    montant_rembourse = 0.0
    cursor = db[COLLECTION_REMBOURSEMENTS].aggregate([
        {"$match": filtre_periode},
        {"$group": {"_id": None, "total": {"$sum": "$montant_paye"}}},
    ])
    async for doc in cursor:
        montant_rembourse = _montant(doc, "total")

    montant_moyen_demande = montant_demande / demandes if demandes > 0 else 0.0
    montant_moyen_rembourse = montant_rembourse / payes if payes > 0 else 0.0
    taux_acceptation = (
        acceptees / (acceptees + rejetees) if (acceptees + rejetees) > 0 else 0.0
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
            "montant_demande": round(_montant(doc, "montant_demande"), 2),
            "rembourses": 0,
            "montant_rembourse": 0.0,
        }

    cursor = db[COLLECTION_REMBOURSEMENTS].aggregate([
        {
            "$match": {
                "date_decision": {"$gte": debut, "$lt": fin},
                "statut": {"$in": list(set(STATUTS_ACCEPTES + (STATUT_PAYE,)))},
            }
        },
        {
            "$group": {
                "_id": {"$dateToString": {"format": "%Y-%m", "date": "$date_decision"}},
                "rembourses": {"$sum": 1},
                "montant_rembourse": {"$sum": "$montant_paye"},
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
                "rembourses": 0,
                "montant_rembourse": 0.0,
            }
        par_mois[mois]["rembourses"] = int(doc["rembourses"])
        par_mois[mois]["montant_rembourse"] = round(
            _montant(doc, "montant_rembourse"), 2
        )

    serie_mensuelle = sorted(par_mois.values(), key=lambda item: item["mois"])
    presents = {item["mois"] for item in serie_mensuelle}
    for mois in _mois_de_lexercice(exercice):
        if mois not in presents:
            serie_mensuelle.append({
                "mois": mois,
                "demandes": 0,
                "montant_demande": 0.0,
                "rembourses": 0,
                "montant_rembourse": 0.0,
            })
    serie_mensuelle.sort(key=lambda item: item["mois"])

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

    repartition_par_prestation: list[dict[str, Any]] = []
    cursor = db[COLLECTION_REMBOURSEMENTS].aggregate([
        {"$match": filtre_periode},
        {"$group": {"_id": "$type_prestation", "total": {"$sum": 1}}},
        {"$sort": {"total": -1}},
    ])
    async for doc in cursor:
        repartition_par_prestation.append(
            {"type_prestation": doc["_id"] or "inconnu", "total": int(doc["total"])}
        )

    return {
        "demandes": int(demandes),
        "acceptees": int(acceptees),
        "rejetees": int(rejetees),
        "en_attente": int(en_attente),
        "payes": int(payes),
        "montant_demande": round(montant_demande, 2),
        "montant_rembourse": round(montant_rembourse, 2),
        "montant_moyen_demande": round(montant_moyen_demande, 2),
        "montant_moyen_rembourse": round(montant_moyen_rembourse, 2),
        "taux_acceptation": round(taux_acceptation, 6),
        "serie_mensuelle": serie_mensuelle,
        "repartition_par_statut": repartition_par_statut,
        "repartition_par_prestation": repartition_par_prestation,
    }


def _format_art(montant: float) -> str:
    return f"{round(montant):,} Ar".replace(",", " ")


def _resume_analytique(
    exercice: int,
    population: dict[str, Any],
    budget: dict[str, Any],
    remboursements: dict[str, Any],
) -> list[dict[str, str]]:
    """Construit un résumé analytique (texte + niveau) à partir des valeurs."""
    evenements: list[dict[str, str]] = []

    credits = budget["credits_ouverts"]
    demandes = remboursements["demandes"]

    if credits == 0 and demandes == 0 and population["total"] == 0:
        evenements.append({
            "cle": "aucune_donnee",
            "niveau": "informations",
            "message": (
                f"Aucune donnée disponible pour l'exercice {exercice}. Importez des "
                "données ou amorcez la base pour alimenter le tableau de bord."
            ),
        })
        return evenements

    if credits > 0:
        taux = budget["taux_execution"]
        if taux >= 0.8:
            niveau = "positif"
            appreciation = "maîtrise satisfaisante des crédits"
        elif taux >= 0.6:
            niveau = "avertissement"
            appreciation = "exécution à surveiller"
        else:
            niveau = "critique"
            appreciation = "exécution nettement sous la cible"
        evenements.append({
            "cle": "taux_execution",
            "niveau": niveau,
            "message": (
                f"Taux d'exécution budgétaire de {taux * 100:.1f} % sur "
                f"{_format_art(credits)} de crédits ouverts : {appreciation}."
            ),
        })

        if budget["solde"] < 0:
            evenements.append({
                "cle": "depassement",
                "niveau": "critique",
                "message": (
                    f"Dépassement budgétaire de {_format_art(-budget['solde'])} : les "
                    "dépenses exécutées excèdent les crédits ouverts."
                ),
            })
        elif budget["engage"] / credits >= 0.95:
            evenements.append({
                "cle": "engagement_eleve",
                "niveau": "avertissement",
                "message": (
                    f"{budget['engage'] / credits * 100:.1f} % des crédits sont déjà "
                    f"engagés ; il reste {_format_art(budget['disponible'])} disponibles."
                ),
            })
        elif budget["disponible"] > 0:
            evenements.append({
                "cle": "disponible",
                "niveau": "positif",
                "message": (
                    f"{_format_art(budget['disponible'])} de crédits encore disponibles "
                    "après engagements sur l'exercice."
                ),
            })

        repartition = budget["repartition_par_type"]
        if repartition and budget["execute"] > 0:
            dominant = repartition[0]
            evenements.append({
                "cle": "type_dominant",
                "niveau": "informations",
                "message": (
                    f"Le type de dépense dominant est « {dominant['type']} » "
                    f"({dominant['montant'] / budget['execute'] * 100:.0f} % de l'exécution)."
                ),
            })
    else:
        evenements.append({
            "cle": "aucun_budget",
            "niveau": "informations",
            "message": f"Aucun crédit voté (LFI/LFR) pour l'exercice {exercice}.",
        })

    if demandes > 0:
        taux_acceptation = remboursements["taux_acceptation"]
        if taux_acceptation >= 0.75:
            niveau = "positif"
        elif taux_acceptation >= 0.5:
            niveau = "avertissement"
        else:
            niveau = "critique"
        evenements.append({
            "cle": "taux_acceptation",
            "niveau": niveau,
            "message": (
                f"{_format_art(remboursements['montant_demande'])} demandés sur "
                f"{demandes} demandes de remboursement ; taux d'acceptation de "
                f"{taux_acceptation * 100:.1f} %."
            ),
        })

        if remboursements["payes"] > 0 and remboursements["montant_rembourse"] > 0:
            evenements.append({
                "cle": "montant_moyen",
                "niveau": "informations",
                "message": (
                    f"Remboursement moyen de "
                    f"{_format_art(remboursements['montant_moyen_rembourse'])} "
                    f"sur {remboursements['payes']} dossiers payés."
                ),
            })

        if remboursements["en_attente"] > 0:
            evenements.append({
                "cle": "en_attente",
                "niveau": "avertissement",
                "message": (
                    f"{remboursements['en_attente']} demandes encore en attente de "
                    "traitement à la clôture de la période."
                ),
            })

    if population["total"] > 0:
        part_actifs = population["actifs"] / population["total"] * 100
        evenements.append({
            "cle": "population",
            "niveau": "informations",
            "message": (
                f"Population de {population['total']} bénéficiaires recensés à fin "
                f"d'exercice ({part_actifs:.0f} % d'actifs, "
                f"{population['pensionnes']} pensionnés)."
            ),
        })

    return evenements


async def calculer_synthese(exercice: Optional[int] = None) -> dict[str, Any]:
    """Calcule la synthèse complète du tableau de bord pour un exercice.

    Si `exercice` est absent, l'exercice le plus récent présent en base est
    utilisé (sinon l'année courante).
    """
    if exercice is None:
        disponibles = await analyser_exercices()
        exercice = disponibles[0] if disponibles else datetime.now(timezone.utc).year
    exercice = int(exercice)

    population = await _population(exercice)
    budget = await _budget(exercice)
    remboursements = await _remboursements(exercice)
    analytique = _resume_analytique(exercice, population, budget, remboursements)

    return {
        "exercice": exercice,
        "calcule_le": datetime.now(timezone.utc).isoformat(),
        "population": population,
        "budget": budget,
        "remboursements": remboursements,
        "analytique": analytique,
    }