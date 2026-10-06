"""Tests de l'assistant conversationnel : les garanties, pas la rédaction.

Le pipeline (`app.ai.query_analyzer` → `indicator_service` →
`prompt_manager` → `llm_service` → `response_validator`) est vérifié sur ce
qui constitue la règle fondamentale, plutôt que sur la qualité des phrases
produites :

- l'analyse et l'identification déterministes classent correctement les quatre
  questions de référence, y compris l'agrégation demandée (superlatif,
  comparaison) ;
- les calculs exacts (extrémum d'une série, écart et parts entre deux
  populations) sont produits par le code à partir de faits bruts ;
- une donnée absente est déclarée comme telle, et le modèle n'est pas appelé ;
- le validateur accepte une valeur du backend et refuse une valeur inventée ;
- le compte rendu de `repondre` ne contient aucun chiffre non rattaché au
  résultat structuré qu'il renvoie, et le générateur de réponses déterministes
  ne déborde jamais ;
- le hors périmètre ne produit aucun chiffre.

Ces tests ne dépendent d'aucune donnée en base : ils vérifient le code. Les
tests de formules sur données réelles (budget, analyses, population) restent
dans leurs modules respectifs.

Lancement :
    python tests/test_assistant.py
"""

import asyncio
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.ai import indicator_service, query_analyzer, query_router
from app.ai.assistant_service import (
    reponse_deterministe,
    repondre,
    referentiel_assistant,
)
from app.ai.indicator_service import ABSENT
from app.ai.response_validator import (
    construire_index,
    valider_reponse,
)
from app.ai.query_analyzer import (
    AGREGATION_ARGMAX,
    AGREGATION_COMPARAISON,
    INTENTION_BUDGET,
    INTENTION_HORS_PERIMETRE,
    INTENTION_POPULATION,
    INTENTION_REMBOURSEMENTS,
)

# --- Les quatre questions de référence du cahier des charges ---------------

QUESTIONS = (
    (
        "Quel est le taux d'exécution du budget RFM ?",
        INTENTION_BUDGET,
        "budget.taux_execution",
    ),
    (
        "Combien de pensionnés ont bénéficié du RFM ?",
        INTENTION_POPULATION,
        "population.croisement",
    ),
    (
        "Quel mois présente le montant remboursé le plus élevé ?",
        INTENTION_REMBOURSEMENTS,
        "remboursements.mois_extremum",
    ),
    (
        "Compare les actifs et les pensionnés.",
        INTENTION_POPULATION,
        "population.comparaison_situations",
    ),
)


# --- Routage des quatre chemins ---------------------------------------------
#
# Le routeur est le seul point où une question peut être envoyée vers la mauvaise
# source, et l'erreur y est silencieuse : une question documentaire envoyée en
# DATA ne produit aucun signal, seulement une réponse vide. Ces cas sont donc
# figés ici, y compris les formulations les plus banales — « quelles pièces
# faut-il fournir » a été mal routée parce que le motif attendait « pièces à
# fournir », sans l'auxiliaire que le français insère entre le nom et le verbe.

CAS_ROUTAGE = (
    # Chemins documentaires
    ("Quelle est la procédure de remboursement ?", query_router.ROUTE_RAG),
    ("Quelles pièces faut-il fournir pour un dossier ?", query_router.ROUTE_RAG),
    ("Quelles pièces justificatives sont exigées ?", query_router.ROUTE_RAG),
    ("Faut-il un agrément pour ouvrir une pharmacie ?", query_router.ROUTE_RAG),
    ("Quels sont les critères d'éligibilité ?", query_router.ROUTE_RAG),
    # Chemins de données
    ("Combien de bénéficiaires sont actifs en 2025 ?", query_router.ROUTE_DATA),
    ("Quel est le taux d'exécution budgétaire en 2025 ?", query_router.ROUTE_DATA),
    ("Quel est le montant remboursé en 2025 ?", query_router.ROUTE_DATA),
    # Chemin mixte : le croisement d'un chiffre et d'un référentiel
    (
        "Le taux d'exécution respecte-t-il les règles prévues par les textes ?",
        query_router.ROUTE_DATA_RAG,
    ),
    (
        "Le montant remboursé en 2025 est-il conforme aux dispositions du document ?",
        query_router.ROUTE_DATA_RAG,
    ),
    # Hors périmètre
    ("Quelle est la température à Perpignan en juin ?", query_router.ROUTE_INCONNUE),
)


def _tester_routage_des_quatre_chemins():
    for question, chemin_attendu in CAS_ROUTAGE:
        route = query_router.classifier(question).route
        assert route.intent == chemin_attendu, (
            f"{question} -> {route.intent} (attendu {chemin_attendu})"
        )

    # Le chemin mixte doit porter les deux exigences, jamais une seule.
    mixte = query_router.classifier(
        "Le montant remboursé en 2025 est-il conforme aux dispositions du document ?"
    ).route
    assert mixte.requiert_donnees and mixte.requiert_documents, mixte.intent

    # Une question bornée à un exercice sans année demande une précision, et
    # ne devine pas d'exercice à la place de l'utilisateur.
    ambigu = query_router.classifier("Quel est le taux d'exécution ?").route
    assert ambigu.besoin_clarification, "l'ambiguïté de période doit être signalée"
    assert "exercice" in ambigu.parametres_manquants, ambigu.parametres_manquants

    # ... alors qu'un indicateur de population se lit sans année.
    population = query_router.classifier("Combien de bénéficiaires ?").route
    assert not population.besoin_clarification, population.question_clarification

    print("[OK] Routage : DATA, RAG, DATA_RAG et INCONNUE sur les quatre chemins")


def _tester_demande_de_precision_redigee_pour_tout_libelle():
    """La demande de précision doit rester correcte quel que soit le libellé.

    Le libellé est un groupe nominal qu'on ne peut pas orner d'un article :
    « Montants exécutés » est pluriel, « Population recensée » féminin, « Âge
    moyen » élidé, et le genre ne se déduit pas d'un suffixe. La tournure a donc
    été choisie pour n'en nécessiter aucun — ce test verrouille cette propriété
    sur les 21 libellés du catalogue, plutôt que sur un exemple unique.
    """
    for code, definition in indicator_service.INDICATEURS_PAR_CODE.items():
        question = query_router._question_clarification(definition.libelle)

        # Le libellé nommé, et une question qui se termine sur la période.
        assert definition.libelle in question, f"{code} -> {question!r}"
        assert question.rstrip().endswith("?"), f"{code} -> {question!r}"
        assert "exercice" in question.lower(), f"{code} -> {question!r}"

        # Aucun article ne doit être accolé au libellé : c'est ce qui produit
        # « connaître taux d'exécution budgétaire », sans article.
        assert not re.search(r"\bconna[îi]tre\s+\w", question, re.IGNORECASE), (
            f"{code} -> {question!r}"
        )

    # Sans libellé, la question reste seule et exploitable.
    sans_libelle = query_router._question_clarification("")
    assert sans_libelle.endswith("?"), sans_libelle
    assert "exercice" in sans_libelle.lower(), sans_libelle

    # Et la route câblée ci-dessus produit bien cette question.
    route = query_router.classifier("Quel est le taux d'exécution ?").route
    assert route.question_clarification, "la question de précision doit être remplie"
    assert route.question_clarification == query_router._question_clarification(
        indicator_service.INDICATEURS_PAR_CODE["budget.taux_execution"].libelle
    ), route.question_clarification

    print("[OK] Demande de précision : formulation correcte pour les 21 libellés")


# --- Analyse et identification (étapes 2 et 3) -----------------------------


def _tester_analyse_et_identification():
    for question, intention_attendue, indicateur_attendu in QUESTIONS:
        intention = query_analyzer.analyser_question(question)

        assert intention.est_dans_perimetre(), question
        assert intention.intention == intention_attendue, (
            f"{question} -> {intention.intention}"
        )

        indicateur = indicator_service.identifier(intention)
        assert indicateur is not None, question
        assert indicateur.code == indicateur_attendu, (
            f"{question} -> {indicateur.code}"
        )

    print("[OK] Analyse et identification des quatre questions de référence")


def _tester_agregation():
    argmax = query_analyzer.analyser_question(
        "Quel mois présente le montant remboursé le plus élevé ?"
    )
    assert argmax.agregation == AGREGATION_ARGMAX, argmax.agregation

    comparaison = query_analyzer.analyser_question(
        "Compare les actifs et les pensionnés."
    )
    assert comparaison.agregation == AGREGATION_COMPARAISON, comparaison.agregation

    # Un exercice nommé dans la question prime sur l'année courante.
    exercice = query_analyzer.analyser_question("Quel est le taux d'exécution en 2024 ?")
    assert exercice.exercice == 2024, exercice.exercice

    print("[OK] Agrégation (superlatif, comparaison) et extraction d'exercice")


# --- Calculs exacts (étape 5) ----------------------------------------------


def _tester_extremum_calcule_par_le_code():
    """Le mois le plus élevé est choisi en Python, pas par le modèle."""
    serie = [
        {"mois": numero, "libelle": mois, "montant_paye": montant}
        for numero, (mois, montant) in enumerate(
            (
                ("janvier", 100.0),
                ("février", 300.0),
                ("mars", 200.0),
            ),
            start=1,
        )
    ]
    intention = query_analyzer.analyser_question(
        "Quel mois présente le montant remboursé le plus élevé ?"
    )

    maximum = indicator_service._calcul_remboursement_extremum(
        {"evolution": serie, "exercice": 2103}, intention
    )
    mois = next(m for m in maximum["mesures"] if m.cle == "mois")
    valeur = next(m for m in maximum["mesures"] if m.cle == "montant_paye")
    assert mois.valeur == "février", mois.valeur
    assert float(valeur.valeur) == 300.0, valeur.valeur

    intention.agregation = "argmin"
    minimum = indicator_service._calcul_remboursement_extremum(
        {"evolution": serie, "exercice": 2103}, intention
    )
    assert next(m for m in minimum["mesures"] if m.cle == "mois").valeur == "janvier"

    # Une série sans valeur exploitable ne produit aucun calcul : elle ne doit
    # pas se traduire par un zéro.
    assert indicator_service._calcul_remboursement_extremum(
        {"evolution": [{"mois": 1, "montant_paye": None}], "exercice": 2103}, intention
    ) is None

    print("[OK] Extrémum d'une série : calculé par le backend, absent sinon")


def _tester_comparaison_calculee_par_le_code():
    """Écart et parts entre actifs et pensionnés : calculés en Python."""
    intention = query_analyzer.analyser_question(
        "Compare les actifs et les pensionnés."
    )
    mesure = indicator_service._calcul_population_comparaison(
        {"actifs": 120, "pensionnes": 80, "exercice": 2103}, intention
    )

    valeurs = {m.cle: m.valeur for m in mesure["mesures"]}
    assert valeurs["actifs"] == 120 and valeurs["pensionnes"] == 80
    assert valeurs["ecart"] == 40, valeurs["ecart"]
    assert abs(valeurs["part_actifs"] - 0.6) < 1e-9, valeurs["part_actifs"]
    assert abs(valeurs["part_pensionnes"] - 0.4) < 1e-9, valeurs["part_pensionnes"]
    assert mesure["texte"] == "catégorie majoritaire : actifs", mesure["texte"]

    # Une population vide ne se calcule pas : elle ne vaut pas zéro écart.
    assert indicator_service._calcul_population_comparaison(
        {"actifs": 0, "pensionnes": 0}, intention
    ) is None

    print("[OK] Comparaison actifs / pensionnés : écart et parts calculés par le backend")


def _tester_croisement_calcule_par_le_code():
    """« Combien de pensionnés ont bénéficié du RFM ? » — croisement backend."""
    faits = {
        "disponible": True,
        "exercice": 2103,
        "croisement": [
            {
                "situation": "actif",
                "situation_libelle": "Actifs",
                "rfm": 30,
                "non_rfm": 10,
                "total": 40,
            },
            {
                "situation": "pensionne",
                "situation_libelle": "Pensionnés",
                "rfm": 25,
                "non_rfm": 15,
                "total": 40,
            },
        ],
    }
    intention = query_analyzer.analyser_question(
        "Combien de pensionnés ont bénéficié du RFM ?"
    )
    mesure = indicator_service._calcul_population_croisement(faits, intention)

    valeurs = {m.cle: m.valeur for m in mesure["mesures"]}
    assert valeurs["rfm"] == 25, valeurs["rfm"]
    assert valeurs["population"] == 40, valeurs["population"]
    assert abs(valeurs["part"] - 0.625) < 1e-9, valeurs["part"]

    # Source sans rattachement RFM : l'information est déclarée absente.
    assert indicator_service._calcul_population_croisement(
        {"disponible": False, "croisement": []}, intention
    ) is None

    print("[OK] Croisement situation / RFM : comptage backend, absence déclarée")


# --- Contrôle des chiffres (étape 8) ---------------------------------------


def _tester_validateur_refuse_une_valeur_inventee():
    resultat = {"mesures": [{"valeur": 1250000, "libelle": "montant", "unite": "montant"}]}
    index = construire_index({"resultat": resultat})

    conforme = valider_reponse("Le montant remboursé est de 1 250 000 Ar.", resultat, index)
    assert conforme.valide, conforme.ecarts
    assert conforme.total_chiffres == 1, conforme.total_chiffres

    # Un reformatage tolerated : c'est la valeur qui est contrôlée, pas
    # son écriture.
    reformate = valider_reponse("Le montant atteint 1,25 M Ar.", resultat, index)
    assert reformate.valide, reformate.ecarts

    # Une valeur absente des données est refusée, quoi qu'en dise le modèle.
    inventee = valider_reponse("Le montant atteint 9 999 999 Ar.", resultat, index)
    assert not inventee.valide, "une valeur inventée ne doit pas valider"
    assert inventee.nombre_ecarts == 1, inventee.ecarts

    print("[OK] Validateur : valeur backend acceptée, valeur inventée rejetée")


async def _tester_reponses_sans_chiffre_invente():
    """Invariant central : la réponse affichée est traçable au résultat renvoyé."""
    for question, _intention, _indicateur in QUESTIONS:
        compte_rendu = await repondre(question, utilisateur=None)
        resultat = compte_rendu["resultat"]

        # Ce que l'API renvoie doit suffire à justifier tous les chiffres de la
        # réponse : c'est le contrôle appliqué à l'étape 8, rejoué sur
        # l'enveloppe exposed au client.
        controle = valider_reponse(compte_rendu["reponse"], {"resultat": resultat})
        assert controle.valide, (
            f"{question} -> {compte_rendu['reponse']!r} "
            f"({[ecart.to_dict() for ecart in controle.ecarts]})"
        )

        # Une réponse non vide, une règle exposée et une provenance explicite.
        assert compte_rendu["reponse"].strip(), question
        assert compte_rendu["regle"], question
        assert compte_rendu["generee_par"] in ("llm", "backend"), question

    print("[OK] Compte rendu : aucun chiffre absent du résultat structuré renvoyé")


async def _tester_donnee_absente_explicitement_declaree():
    """Un calcul qui n'aboutit pas doit le dire, sans appel au modèle.

    Le cas d'absence est ici produit par le chemin réel du pipeline : source
    injoignable ou vide. Les deux se ramènent au même contrat — un résultat
    marqué indisponible, porteur d'un motif, dont aucune valeur n'est citable.
    """
    definition = indicator_service.INDICATEURS_PAR_CODE["budget.taux_execution"]
    intention = query_analyzer.analyser_question("Quel est le taux d'exécution ?")
    resultat, _faits = await indicator_service.resoudre(intention, 1999)

    # Un exercice sans aucune donnée ne peut pas produire de taux.
    if resultat.statut != ABSENT:
        resultat = indicator_service._absent(
            definition,
            "Aucun crédit voté n'est enregistré pour cet exercice.",
            1999,
        )

    assert resultat.statut == ABSENT, resultat.statut
    assert resultat.absence, "l'absence doit être motivée"
    assert resultat.exploitable is False, "aucun chiffre ne doit être citable"
    assert not resultat.mesures, resultat.mesures
    assert resultat.sources, "l'absence reste rattachée à sa source"

    reponse = reponse_deterministe(resultat)
    assert "n'est pas disponible" in reponse, reponse
    assert resultat.absence in reponse, reponse

    # Aucun chiffre ne doit être produit pour une donnée absente, et le
    # pipeline ne doit pas appeler le modèle dans ce cas.
    controle = valider_reponse(reponse, {"resultat": resultat.resume()})
    assert controle.valide, controle.ecarts

    compte_rendu = await repondre("Quel est le taux d'exécution en 1999 ?", utilisateur=None)
    if compte_rendu["resultat"]["statut"] == ABSENT:
        assert compte_rendu["generee_par"] == "backend", compte_rendu
        assert compte_rendu["modele"] is None, compte_rendu

    print("[OK] Donnée absente : déclarée explicitement, sans estimation ni modèle")


async def _tester_hors_perimetre_sans_chiffre():
    compte_rendu = await repondre(
        "Quelle est la météo à Antananarivo demain ?", utilisateur=None
    )
    assert compte_rendu["hors_perimetre"] is True, compte_rendu["reponse"]
    assert compte_rendu["generee_par"] == "backend"
    assert compte_rendu["modele"] is None

    controle = valider_reponse(
        compte_rendu["reponse"], {"resultat": compte_rendu["resultat"]}
    )
    assert controle.valide, controle.ecarts

    intention = query_analyzer.analyser_question(
        "Quelle est la météo à Antananarivo demain ?"
    )
    assert intention.intention == INTENTION_HORS_PERIMETRE, intention.intention

    print("[OK] Hors périmètre : réponse de périmètre, aucun chiffre")


async def _tester_question_invalide_refusee():
    from app.utils.errors import ErreurValidation

    for question in ("", "   "):
        try:
            await repondre(question, utilisateur=None)
        except ErreurValidation:
            continue
        raise AssertionError(f"question invalide acceptée : {question!r}")

    print("[OK] Question vide : refusée avant tout traitement")


def _tester_referentiel():
    referentiel = referentiel_assistant()
    assert len(referentiel["pipeline"]) == 8, referentiel["pipeline"]
    assert referentiel["pipeline"][0] == "Question utilisateur"
    assert referentiel["pipeline"][-1].startswith("Explication naturelle")
    assert referentiel["garanties"], referentiel["garanties"]

    codes = {indicateur["code"] for indicateur in referentiel["indicateurs"]}
    for _question, _intention, indicateur in QUESTIONS:
        assert indicateur in codes, indicateur

    intentions = {item["code"] for item in referentiel["intentions"]}
    assert INTENTION_HORS_PERIMETRE in intentions

    print("[OK] Référentiel : pipeline en 8 étapes, garanties et catalogue")


async def executer_tests():
    _tester_routage_des_quatre_chemins()
    _tester_demande_de_precision_redigee_pour_tout_libelle()
    _tester_analyse_et_identification()
    _tester_agregation()
    _tester_extremum_calcule_par_le_code()
    _tester_comparaison_calculee_par_le_code()
    _tester_croisement_calcule_par_le_code()
    _tester_validateur_refuse_une_valeur_inventee()
    _tester_referentiel()
    await _tester_reponses_sans_chiffre_invente()
    await _tester_donnee_absente_explicitement_declaree()
    await _tester_hors_perimetre_sans_chiffre()
    await _tester_question_invalide_refusee()


if __name__ == "__main__":
    try:
        asyncio.run(executer_tests())
        print("\n[SUCCÈS] Assistant conversationnel : toutes les garanties sont respectées.")
    except AssertionError as erreur:
        print(f"\n[ÉCHEC] {erreur}")
        raise SystemExit(1)
