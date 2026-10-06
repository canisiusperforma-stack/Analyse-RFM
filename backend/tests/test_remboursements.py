"""Tests de l'analyse des remboursements : formules côté backend.

Le jeu est inséré sur des exercices dédiés (2101/2100) avec des
bénéficiaires dédiés ; le nettoyage est ciblé sur les seuls documents
créés (aucun impact sur les données de démonstration).

Vérifie :
- volumes par statut (demandes, acceptées, refusées, en attente, payées) ;
- montants : totaux, moyennes, médianes, minimums, maximums ;
- répartitions par statut, type de dépense et circuit ;
- série mensuelle (demandes, montants, payés) ;
- comparaison avec l'exercice précédent ;
- la liste : recherche, filtres (statut, type, circuit, bornes de montant),
  tri par plusieurs champs et pagination ;
- les routes (statistiques, liste, exercices) et la permission
  `remboursements:voir`.

Lancement :
    python tests/test_remboursements.py
"""

import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bson import Decimal128, ObjectId

from app.api.routes.remboursements import (
    exercices as route_exercices,
    lister as route_lister,
    statistiques as route_statistiques,
)
from app.database import connecter_database, fermer_database, obtenir_database
from app.services.remboursement_service import (
    COLLECTION_BENEFICIAIRES,
    COLLECTION_REMBOURSEMENTS,
    exercices_remboursements,
    lister_remboursements,
    statistiques_remboursements,
)

EXERCICE = 2101
PRECEDENT = 2100


def _utc(annee: int, mois: int, jour: int) -> datetime:
    return datetime(annee, mois, jour, tzinfo=timezone.utc)


def _art(valeur: int) -> Decimal128:
    return Decimal128(str(valeur))


def _proche(valeur: float, attendu: float, tol: float = 0.01) -> bool:
    return abs(valeur - attendu) <= tol


async def _inserer_jeu():
    db = obtenir_database()
    await _nettoyer_jeu()

    beneficiaires = [
        {
            "matricule": "RFM-T-001", "nom": "RAKOTO", "prenom": "Hery",
            "date_naissance": _utc(1978, 4, 12), "genre": "M",
            "situation": "actif", "categorie": "fonctionnaire",
            "direction": "Direction test", "cin": "1",
            "statut_dossier": "actif",
            "created_at": _utc(2100, 6, 15), "updated_at": _utc(2100, 6, 15),
        },
        {
            "matricule": "RFM-T-002", "nom": "RABE", "prenom": "Lala",
            "date_naissance": _utc(1981, 1, 1), "genre": "F",
            "situation": "actif", "categorie": "contractuel",
            "direction": "Direction test", "cin": "2",
            "statut_dossier": "actif",
            "created_at": _utc(2100, 3, 1), "updated_at": _utc(2100, 3, 1),
        },
    ]
    resultat = await db[COLLECTION_BENEFICIAIRES].insert_many(beneficiaires)
    ids = list(resultat.inserted_ids)
    a, b = ids

    dossiers = [
        # (numéro, bénéficiaire, type, circuit, date_demande, date_decision,
        #  demande, accordée, payée, statut, motif)
        ("RM-2101-01", a, "soins", "circuit_normal", (2, 15), (3, 2),
         1_000_000, 900_000, 900_000, "paye", None),
        ("RM-2101-02", a, "hospitalisation", "circuit_accelere", (3, 10), (3, 20),
         2_000_000, 1_800_000, 1_800_000, "paye", None),
        ("RM-2101-03", b, "pharmacie", "circuit_normal", (4, 5), (4, 15),
         500_000, 400_000, None, "valide", None),
        ("RM-2101-04", a, "soins", "circuit_normal", (5, 1), (5, 10),
         300_000, None, None, "refuse", "Justificatifs incomplets"),
        ("RM-2101-05", b, "prothese", "circuit_accelere", (6, 1), None,
         700_000, None, None, "soumis", None),
        ("RM-2101-06", a, "soins", "circuit_normal", (7, 1), (7, 5),
         200_000, 150_000, 150_000, "paye", None),
        ("RM-2100-99", b, "soins", "circuit_normal", (11, 1), None,
         200_000, None, None, "soumis", None),
    ]

    remboursements = []
    for (numero, beneficiaire_id, type_prestation, circuit,
         (mois_demande, jour_demande), decision,
         montant_demande, montant_accordee, montant_paye, statut, motif) in dossiers:
        exercice = int(numero.split("-")[1])
        date_demande = _utc(exercice, mois_demande, jour_demande)
        date_decision = (
            _utc(exercice, decision[0], decision[1]) if decision else None
        )
        remboursements.append({
            "numero_dossier": numero,
            "beneficiaire_id": beneficiaire_id,
            "type_prestation": type_prestation,
            "circuit": circuit,
            "date_demande": date_demande,
            "date_decision": date_decision,
            "montant_demande": _art(montant_demande),
            "montant_accordee": _art(montant_accordee) if montant_accordee is not None else None,
            "montant_paye": _art(montant_paye) if montant_paye is not None else None,
            "statut": statut,
            "motif_refus": motif,
            "pieces": [],
            "valide_par": None,
            "created_at": date_demande,
            "updated_at": date_decision or date_demande,
        })
    await db[COLLECTION_REMBOURSEMENTS].insert_many(remboursements)

    _jeu["ids_beneficiaires"] = ids
    _jeu["ids_remboursements"] = [
        document["numero_dossier"] for document in remboursements
    ]


_jeu: dict = {}


async def _nettoyer_jeu():
    db = obtenir_database()
    if _jeu.get("ids_beneficiaires"):
        await db[COLLECTION_BENEFICIAIRES].delete_many(
            {"_id": {"$in": _jeu["ids_beneficiaires"]}}
        )
    if _jeu.get("ids_remboursements"):
        await db[COLLECTION_REMBOURSEMENTS].delete_many(
            {"numero_dossier": {"$in": _jeu["ids_remboursements"]}}
        )
    _jeu.clear()


async def _tester_volumes():
    stats = await statistiques_remboursements(EXERCICE)
    assert stats["demandes"] == 6, stats
    assert stats["acceptees"] == 4, stats  # valide + paye
    assert stats["rejetees"] == 1, stats
    assert stats["en_attente"] == 1, stats  # soumis
    assert stats["payes"] == 3, stats
    assert abs(stats["taux_acceptation"] - 0.8) < 1e-6, stats
    print("[OK] Volumes par statut et taux d'acceptation")


async def _tester_montants():
    stats = await statistiques_remboursements(EXERCICE)
    demande = stats["montants"]["demande"]
    assert demande["montants"] == 6, demande
    assert demande["total"] == 4_700_000, demande
    assert _proche(demande["moyenne"], 4_700_000 / 6), demande
    assert demande["mediane"] == 600_000, demande
    assert demande["minimum"] == 200_000, demande
    assert demande["maximum"] == 2_000_000, demande

    accordee = stats["montants"]["accordee"]
    assert accordee["montants"] == 4, accordee  # uniquement acceptées
    assert accordee["total"] == 3_250_000, accordee
    assert accordee["mediane"] == 650_000, accordee
    assert accordee["minimum"] == 150_000 and accordee["maximum"] == 1_800_000, accordee

    paye = stats["montants"]["paye"]
    assert paye["montants"] == 3, paye
    assert paye["total"] == 2_850_000, paye
    assert paye["moyenne"] == 950_000, paye
    assert paye["mediane"] == 900_000, paye
    print("[OK] Montants : totaux, moyennes, médianes, minimums, maximums")


async def _tester_repartitions():
    stats = await statistiques_remboursements(EXERCICE)
    statuts = {item["statut"]: item["total"] for item in stats["repartition_par_statut"]}
    assert statuts == {"paye": 3, "valide": 1, "refuse": 1, "soumis": 1}, statuts

    types = {item["type_prestation"]: item for item in stats["repartition_par_type"]}
    assert types["soins"]["total"] == 3, types
    assert types["soins"]["montant_demande"] == 1_500_000, types["soins"]
    assert types["soins"]["montant_paye"] == 1_050_000, types["soins"]
    assert types["hospitalisation"]["total"] == 1, types

    circuits = {item["circuit"]: item["total"] for item in stats["repartition_par_circuit"]}
    assert circuits == {"circuit_normal": 4, "circuit_accelere": 2}, circuits
    print("[OK] Répartitions par statut, type de dépense et circuit")


async def _tester_serie():
    stats = await statistiques_remboursements(EXERCICE)
    serie = {item["mois"]: item for item in stats["serie_mensuelle"]}
    assert len(stats["serie_mensuelle"]) == 12, stats["serie_mensuelle"]
    assert serie["2101-02"]["demandes"] == 1, serie["2101-02"]
    assert serie["2101-02"]["montant_demande"] == 1_000_000, serie["2101-02"]
    assert serie["2101-03"]["payes"] == 2, serie["2101-03"]
    assert serie["2101-03"]["montant_paye"] == 2_700_000, serie["2101-03"]
    assert serie["2101-07"]["payes"] == 1, serie["2101-07"]
    assert serie["2101-07"]["montant_paye"] == 150_000, serie["2101-07"]
    assert serie["2101-01"]["demandes"] == 0, serie["2101-01"]
    assert serie["2101-12"]["demandes"] == 0, serie["2101-12"]
    print("[OK] Série mensuelle : demandes, montants et payés")


async def _tester_comparaison():
    stats = await statistiques_remboursements(EXERCICE)
    comparaison = stats["comparaison"]
    assert comparaison is not None, stats
    assert comparaison["exercice_precedent"] == PRECEDENT, comparaison
    assert comparaison["demandes_precedent"] == 1, comparaison
    assert comparaison["montant_demande_precedent"] == 200_000, comparaison
    assert comparaison["payes_precedent"] == 0, comparaison
    assert comparaison["ecart_demandes"] == 5, comparaison
    assert comparaison["ecart_montant_demande"] == 4_500_000, comparaison
    assert comparaison["ecart_montant_paye"] == 2_850_000, comparaison
    assert abs(comparaison["variation_pct_demandes"] - 5.0) < 1e-6, comparaison
    assert comparaison["variation_pct_payes"] is None, comparaison
    assert abs(compara_variation_montant(comparaison, "montant_demande") - 22.5) < 1e-6, comparaison
    assert comparaison["variation_pct_montant_paye"] is None, comparaison
    print("[OK] Comparaison avec l'exercice précédent")


def compara_variation_montant(comparaison: dict, cle: str):
    return comparaison[f"variation_pct_{cle}"]


async def _tester_liste():
    def numeros(items):
        return [item["numero_dossier"] for item in items]

    # Tri par défaut : date de demande décroissante.
    resultat = await lister_remboursements(exercice=EXERCICE, limite=5)
    assert resultat["total"] == 6, resultat
    assert resultat["items"][0]["numero_dossier"] == "RM-2101-06", resultat
    assert resultat["items"][0]["beneficiaire"]["nom"] == "RAKOTO", resultat

    # Recherche par nom du bénéficiaire.
    par_nom = await lister_remboursements(exercice=EXERCICE, recherche="RAKOTO")
    assert par_nom["total"] == 4, par_nom
    assert all(item["beneficiaire"]["nom"] == "RAKOTO" for item in par_nom["items"])

    # Recherche par n° de dossier.
    par_numero = await lister_remboursements(exercice=EXERCICE, recherche="RM-2101-03")
    assert par_numero["total"] == 1, par_numero
    assert par_numero["items"][0]["statut"] == "valide", par_numero

    # Filtres : statut, type, circuit, bornes de montant.
    assert (await lister_remboursements(exercice=EXERCICE, statut="paye"))["total"] == 3
    assert (
        await lister_remboursements(exercice=EXERCICE, type_prestation="soins")
    )["total"] == 3
    assert (
        await lister_remboursements(exercice=EXERCICE, circuit="circuit_accelere")
    )["total"] == 2
    assert (
        await lister_remboursements(exercice=EXERCICE, montant_min=1_000_000)
    )["total"] == 2
    assert (
        await lister_remboursements(exercice=EXERCICE, montant_max=400_000)
    )["total"] == 2

    # Tri par montant croissant / décroissant.
    croissant = await lister_remboursements(
        exercice=EXERCICE, tri="montant_demande", ordre="asc"
    )
    assert croissant["items"][0]["montant_demande"] == 200_000, croissant
    decroissant = await lister_remboursements(
        exercice=EXERCICE, tri="montant_demande", ordre="desc"
    )
    assert decroissant["items"][0]["montant_demande"] == 2_000_000, decroissant

    # Pagination.
    page1 = await lister_remboursements(exercice=EXERCICE, limite=2, saut=0)
    page2 = await lister_remboursements(exercice=EXERCICE, limite=2, saut=2)
    union = numeros(page1["items"]) + numeros(page2["items"])
    assert len(union) == 4, union
    assert page1["items"][0]["numero_dossier"] != page2["items"][0]["numero_dossier"]
    print("[OK] Liste : recherche, filtres, tri et pagination")


async def _tester_routes_permission():
    utilisateur = {"_id": ObjectId(), "role": "AGENT", "email": "agent@test.mg"}
    stats = await route_statistiques(exercice=EXERCICE, _utilisateur=utilisateur)
    assert stats["exercice"] == EXERCICE
    assert stats["demandes"] == 6 and "montants" in stats

    liste = await route_lister(
        exercice=EXERCICE, _utilisateur=utilisateur,
        statut="paye", limite=2, saut=0, tri="date_demande", ordre="desc",
    )
    assert liste["total"] == 3 and len(liste["items"]) == 2, liste

    disponibles = await exercices_remboursements()
    assert EXERCICE in disponibles and PRECEDENT in disponibles
    assert disponibles == sorted(disponibles, reverse=True), disponibles
    reponse = await route_exercices(_utilisateur=utilisateur)
    assert reponse["exercices"] == disponibles, reponse
    print("[OK] Routes : statistiques, liste, exercices (permission remboursements:voir)")


async def executer_tests():
    await connecter_database()
    try:
        await _inserer_jeu()
        await _tester_volumes()
        await _tester_montants()
        await _tester_repartitions()
        await _tester_serie()
        await _tester_comparaison()
        await _tester_liste()
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
        sys.exit(1)
    print("TEST_REMBOURSEMENTS : OK")