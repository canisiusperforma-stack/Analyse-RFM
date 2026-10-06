"""Tests de l'analyse temporelle : formules côté backend.

Le jeu est inséré sur des exercices dédiés (2103/2102) ; le nettoyage
est ciblé sur les seuls documents créés (aucun impact sur la démo).

Vérifie :
- l'évolution mensuelle : demandes, montants demandés/remboursés, payés,
  moyennes, taux d'exécution et variations d'un mois sur l'autre ;
- la synthèse : totaux, taux d'exécution, moyennes, moyenne mensuelle
  (total / 12 mois) ;
- la comparaison avec l'exercice précédent (écarts et variations) ;
- les routes et la permission `analyses:voir`.

Lancement :
    python tests/test_analyses.py
"""

import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bson import Decimal128, ObjectId

from app.api.routes.analyses import temporelle as route_temporelle
from app.database import connecter_database, fermer_database, obtenir_database
from app.services.analyse_service import analyse_temporelle
from app.services.remboursement_service import (
    COLLECTION_REMBOURSEMENTS,
    _entete,
    exercices_remboursements,
)

EXERCICE = 2103
PRECEDENT = 2102


def _utc(annee: int, mois: int, jour: int) -> datetime:
    return datetime(annee, mois, jour, tzinfo=timezone.utc)


def _art(valeur: int) -> Decimal128:
    return Decimal128(str(valeur))


def _proche(valeur: float, attendu: float, tol: float = 0.01) -> bool:
    return abs(valeur - attendu) <= tol


async def _nettoyer_jeu():
    db = obtenir_database()
    for annee in (EXERCICE, PRECEDENT):
        debut, fin = _entete(annee)
        await db[COLLECTION_REMBOURSEMENTS].delete_many({
            "date_demande": {"$gte": debut, "$lt": fin},
        })


async def _inserer_jeu():
    db = obtenir_database()
    await _nettoyer_jeu()

    beneficiaire = ObjectId()
    remboursements = [
        # Exercice courant 2103.
        ("AT-2103-01", (1, 5), 100_000, 80_000, "paye"),
        ("AT-2103-02", (1, 20), 150_000, None, "valide"),
        ("AT-2103-03", (3, 12), 200_000, 200_000, "paye"),
        # Exercice précédent 2102.
        ("AT-2102-01", (2, 8), 300_000, None, "refuse"),
    ]
    documents = []
    for (numero, (mois, jour), montant_demande, montant_paye, statut) in remboursements:
        exercice = int(numero.split("-")[1])
        documents.append({
            "numero_dossier": numero,
            "beneficiaire_id": beneficiaire,
            "type_prestation": "soins",
            "circuit": "circuit_normal",
            "date_demande": _utc(exercice, mois, jour),
            "date_decision": _utc(exercice, mois, jour + 5),
            "montant_demande": _art(montant_demande),
            "montant_accordee": _art(montant_paye) if montant_paye else None,
            "montant_paye": _art(montant_paye) if montant_paye else None,
            "statut": statut,
            "motif_refus": None,
            "created_at": _utc(exercice, 1, 1),
            "updated_at": _utc(exercice, 1, 1),
        })
    await db[COLLECTION_REMBOURSEMENTS].insert_many(documents)


async def _tester_evolution():
    resultat = await analyse_temporelle(EXERCICE)
    evolution = resultat["evolution"]
    assert len(evolution) == 12, evolution
    assert len(resultat["evolution_precedente"]) == 12

    janvier = evolution[0]
    assert janvier["periode"] == "2103-01" and janvier["libelle"] == "Janv."
    assert janvier["demandes"] == 2
    assert _proche(janvier["montant_demande"], 250_000)
    assert janvier["payes"] == 1
    assert _proche(janvier["montant_paye"], 80_000)
    assert _proche(janvier["taux_execution"], 0.32)
    assert janvier["moyenne"] == 125_000
    assert janvier["moyenne_paye"] == 80_000
    assert janvier["variation_demandes"] is None  # premier mois

    fevrier = evolution[1]
    assert fevrier["demandes"] == 0 and _proche(fevrier["montant_demande"], 0)
    assert fevrier["variation_demandes"] == -1.0  # 0 par rapport à 2

    mars = evolution[2]
    assert mars["demandes"] == 1
    assert _proche(mars["montant_demande"], 200_000)
    assert _proche(mars["montant_paye"], 200_000)
    assert mars["taux_execution"] == 1.0
    assert mars["moyenne"] == 200_000
    assert mars["variation_demandes"] is None  # mois précédent à zéro
    assert mars["variation_montant"] is None
    assert mars["variation_paye"] is None

    assert all(item["libelle"] == ["Janv.", "Févr.", "Mars", "Avr.", "Mai", "Juin",
                                   "Juil.", "Août", "Sept.", "Oct.", "Nov.", "Déc."][item["mois"] - 1]
               for item in evolution)
    print("[OK] Évolution mensuelle : demandes, montants, moyennes, taux, variations")

    return resultat


async def _tester_synthese():
    resultat = await analyse_temporelle(EXERCICE)
    synthese = resultat["synthese"]
    assert synthese["exercice"] == EXERCICE
    assert synthese["demandes"] == 3
    assert synthese["payes"] == 2
    assert _proche(synthese["montant_demande"], 450_000)
    assert _proche(synthese["montant_paye"], 280_000)
    assert _proche(synthese["taux_execution"], 280_000 / 450_000)
    assert synthese["moyenne"] == 150_000
    assert synthese["moyenne_paye"] == 140_000

    moyenne_mensuelle = synthese["moyenne_mensuelle"]
    assert _proche(moyenne_mensuelle["demandes"], 3 / 12)
    assert _proche(moyenne_mensuelle["payes"], 2 / 12)
    assert _proche(moyenne_mensuelle["montant_demande"], 450_000 / 12)
    assert _proche(moyenne_mensuelle["montant_paye"], 280_000 / 12)

    total_evolution_demandes = sum(item["demandes"] for item in resultat["evolution"])
    assert total_evolution_demandes == synthese["demandes"]
    print("[OK] Synthèse : totaux, taux d'exécution, moyennes, moyenne mensuelle")


async def _tester_comparaison():
    resultat = await analyse_temporelle(EXERCICE)
    comparaison = resultat["comparaison"]
    assert comparaison["exercice_precedent"] == PRECEDENT

    demandes = comparaison["demandes"]
    assert demandes["courant"] == 3 and demandes["precedent"] == 1
    assert demandes["ecart"] == 2
    assert demandes["variation_pct"] == 2.0

    montant = comparaison["montant_demande"]
    assert montant["courant"] == 450_000 and montant["precedent"] == 300_000
    assert montant["ecart"] == 150_000
    assert montant["variation_pct"] == 0.5

    paye = comparaison["montant_paye"]
    assert paye["courant"] == 280_000 and paye["precedent"] == 0
    assert paye["ecart"] == 280_000
    assert paye["variation_pct"] is None  # pas de base l'an dernier

    taux = comparaison["taux_execution"]
    assert _proche(taux["courant"], 280_000 / 450_000)
    assert taux["precedent"] == 0.0
    assert _proche(taux["ecart"], 280_000 / 450_000)

    moyenne_mensuelle = comparaison["moyenne_mensuelle"]
    assert _proche(
        moyenne_mensuelle["montant_demande"]["courant"], 450_000 / 12
    )
    assert _proche(
        moyenne_mensuelle["montant_demande"]["precedent"], 300_000 / 12
    )
    assert moyenne_mensuelle["montant_paye"]["variation_pct"] is None
    print("[OK] Comparaison des périodes : exercice courant vs précédent")


async def _tester_routes_permission():
    utilisateur = {"_id": ObjectId(), "role": "AGENT", "email": "agent@test.mg"}
    reponse = await route_temporelle(exercice=EXERCICE, _utilisateur=utilisateur)
    assert reponse["exercice"] == EXERCICE
    assert len(reponse["evolution"]) == 12
    assert reponse["synthese"]["demandes"] == 3

    disponibles = await exercices_remboursements()
    assert EXERCICE in disponibles and PRECEDENT in disponibles
    assert disponibles == sorted(disponibles, reverse=True)
    print("[OK] Routes : analyse temporelle (permission analyses:voir)")


async def executer_tests():
    await connecter_database()
    try:
        await _inserer_jeu()
        await _tester_evolution()
        await _tester_synthese()
        await _tester_comparaison()
        await _tester_routes_permission()
        await _nettoyer_jeu()
    finally:
        await _nettoyer_jeu()
        await fermer_database()


if __name__ == "__main__":
    try:
        asyncio.run(executer_tests())
    except AssertionError as erreur:
        print(f"[ÉCHEC] {erreur}")