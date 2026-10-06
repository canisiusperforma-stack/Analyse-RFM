"""Génère les classeurs Excel d'exercice (jeu de démonstration RFM SRB).

Produit un fichier .xlsx par exercice (2021 → 2024) dans
`backend/data/raw/exercices/`. Chaque classeur contient quatre feuilles, dans
l'ordre des dépendances de déversement :

- `Beneficiaires` (index 0) — feuille importable, alignée sur la projection
  `PROJECTION_IMPORTS` de `app.services.beneficiaires_service` ;
- `Budget` (index 1) — lignes budgétaires votées (LFI / LFR) ;
- `Executions` (index 2) — exécutions mensuelles par phase, rattachées à une
  ligne budgétaire par `(exercice, ligne_budgetaire, nature)` ;
- `Remboursements` (index 3) — dossiers de remboursement de l'exercice,
  rattachés à un bénéficiaire par `matricule`.

L'onglet de chaque feuille est ce que le pipeline de déversement
(`app.imports.cibles`) reconnaît : importer le classeur avec l'option
« déversement » écrit directement dans les quatre collections métier.

Le jeu est déterministe (graine fixe) : deux exécutions produisent des
fichiers identiques. En fin de génération, une passe de contrôle appelle le
propre pipeline d'import (`lire_fichier`, `analyser_colonnes`,
`valider_lignes`, `marquer_doublons`) sur chaque feuille afin de vérifier que
chaque classeur est importable et que les seuls rejets sont ceux voulus.

Lancement (depuis `backend/`) :
    python scripts/generer_exercices.py
"""

from __future__ import annotations

import argparse
import random
import sys
from datetime import date, timedelta
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

RACINE = Path(__file__).resolve().parent.parent
DOSSIER_CIBLE = RACINE / "data" / "raw" / "exercices"

GRAINE = 20210401
EXERCICES: tuple[int, ...] = (2021, 2022, 2023, 2024)
VOLUME_PAR_EXERCICE: dict[int, int] = {2021: 165, 2022: 190, 2023: 218, 2024: 250}

NOMS = [
    "RAKOTO", "RABE", "RAZAFY", "RANDRIA", "ANDRIANJAKA", "RASOAMANANA",
    "RAVELOJAONA", "RATSIMBAZAFY", "RAKOTONDRABE", "RANAIVO", "RASAMIMANANA",
    "ANDRIAMAMONJY", "ANDRIANARIVELO", "RAHERINIAINA", "RANDRIAMANANTSOA",
    "RABARY", "RAZAKARISON", "ANDRIANARISON", "RAJAONARISON", "RATOVOHERY",
    "RAZAFIMANDIMBY", "RAMAROSON", "RAKOTONIRINA", "RANOROSOA", "ANDRINIVO",
    "RAKOTOMALALA", "RAHARIMALALA", "RAJAONARISOA", "RANDRIANASOLO",
    "RAVAOARISOA", "RAKOTONDRAZAKA", "RABEARISOA", "RAZANADRakoto",
]

PRENOMS_HOMMES = [
    "Hery", "Tojo", "Tiana", "Solofo", "Iarivo", "Feno", "Sarobidy",
    "Rija", "Tantely", "Tsiky", "Haja", "Zara", "Toky", "Ny Aina",
    "Fandresena", "Mamy", "Lova", "Andry", "Hery Tiana", "Nirina",
]

PRENOMS_FEMMES = [
    "Lala", "Voahangy", "Noro", "Fara", "Mialy", "Onja", "Hanta", "Vonjy",
    "Mialia", "Vola", "Mamisoa", "Ravaka", "Sitraka", "Soa", "Domoina",
    "Faniry", "Hasina", "Noroa", "Lalaina", "Anjara",
]

DIRECTIONS = [
    "Direction Regionale de l'Education - Vatovavy",
    "Direction Regionale de la Sante - Vatovavy",
    "Direction Regionale de l'Agriculture - Vatovavy",
    "Direction Regionale de l'Administration Generale - Vatovavy",
    "Prefecture de Vatovavy",
    "Tresor Public de Vatovavy",
    "Mairie de Vatovavy",
]

DISTRICTS = [
    "Vatovavy", "Ifanadiana", "Nosy Varika", "Mananjary",
    "Matala", "Ambohitantely", "Vohiparenty",
]

COMMUNES = [
    "Vatovavy", "Antanambao", "Ifanadiana", "Nosy Varika", "Mananjary",
    "Ambohitantely", "Ambalaha", "Tazavato", "Vohiparenty", "Matala",
]

CATEGORIES_ACTIF = ("fonctionnaire", "contractuel")
CATEGORIES_PENSIONNE = ("retraite",)
STATUTS_DOSSIER = ("actif", "suspendu", "clos")

LIGNES_BUDGETAIRES = [
    ("31-01", "31-01-11", "Remboursements de frais de soins - actifs", "fonctionnement", 620_000_000),
    ("31-02", "31-02-12", "Remboursements de frais de soins - pensionnes", "fonctionnement", 710_000_000),
    ("31-03", "31-03-13", "Pharmacie et consommables medicaux", "fonctionnement", 300_000_000),
    ("31-04", "31-04-14", "Hospitalisation et soins lourds", "fonctionnement", 395_000_000),
    ("31-05", "31-05-15", "Protheses et equipements medicaux", "fonctionnement", 138_000_000),
    ("32-01", "32-01-21", "Frais de fonctionnement du service RFM", "fonctionnement", 95_000_000),
    ("33-01", "33-01-31", "Investissement - systeme d'information", "investissement", 72_000_000),
]

PRESTATIONS = {
    "soins": (95_000, 760_000, 0.42),
    "pharmacie": (45_000, 280_000, 0.31),
    "hospitalisation": (950_000, 5_800_000, 0.15),
    "prothese": (780_000, 4_200_000, 0.06),
    "autre": (75_000, 470_000, 0.06),
}

STATUTS_PONDERES = (
    ("paye", 0.61), ("valide", 0.15), ("refuse", 0.10),
    ("en_attente", 0.07), ("soumis", 0.03), ("a_completer", 0.02),
    ("en_cours", 0.02),
)

#: `remboursement_service.STATUTS_*` n'admet que ces sept statuts : toute
#: autre valeur serait comptée nulle part dans l'application.
STATUTS_REMBOURSEMENT = (
    "valide", "paye", "refuse", "soumis", "a_completer", "en_cours",
    "en_attente",
)

assert {s for s, _ in STATUTS_PONDERES} <= set(STATUTS_REMBOURSEMENT)

#: Ordre des phases d'exécution ; la phase n'apparaît qu'une fois la
#: précédente engagée dans l'exercice.
PHASES_EXECUTION = (
    "engagement", "liquidation", "ordonnancement", "paiement",
)
PREMIER_MOIS_PAR_PHASE = {
    "engagement": 1,
    "liquidation": 2,
    "ordonnancement": 3,
    "paiement": 4,
}
#: Part du mois réalisée à chaque phase : l'engagement cumule le plus, le
#: paiement le moins, ce qui donne des taux d'exécution décroissants.
COEF_PAR_PHASE = {
    "engagement": 1.00,
    "liquidation": 0.96,
    "ordonnancement": 0.91,
    "paiement": 0.86,
}

ENTETES_BENEFICIAIRES = [
    "Matricule", "Nom", "Prenom", "Date de naissance", "Genre", "Situation",
    "Categorie", "Statut dossier", "Direction", "Region", "District",
    "Commune", "CIN", "Montant cotisation", "Date d'inscription", "Exercice",
]

ENTETES_BUDGET = [
    "Exercice", "Chapitre", "Ligne budgetaire", "Libelle", "Nature", "Type",
    "Montant vote",
]

ENTETES_EXECUTIONS = [
    "Exercice", "Ligne budgetaire", "Nature", "Mois", "Phase", "Montant",
]

ENTETES_REMBOURSEMENTS = [
    "N° dossier", "Matricule", "Type prestation", "Circuit", "Date demande",
    "Date decision", "Montant demande", "Montant accorde", "Montant paye",
    "Statut", "Motif refus", "Exercice",
]

FORMAT_MONTANT = '# ##0" Ar"'
FORMAT_DATE = "DD/MM/YYYY"

STYLE_ENTETE_FONT = Font(bold=True, color="FFFFFF", size=11)
STYLE_ENTETE_FILL = PatternFill("solid", fgColor="1F4E5F")
STYLE_TITRE_FONT = Font(bold=True, size=13, color="1F4E5F")

LARGEURS = {
    "Matricule": 18, "Nom": 20, "Prenom": 16, "Date de naissance": 18,
    "Genre": 8, "Situation": 12, "Categorie": 14, "Statut dossier": 15,
    "Direction": 52, "Region": 14, "District": 16, "Commune": 16, "CIN": 16,
    "Montant cotisation": 20, "Date d'inscription": 18, "Exercice": 11,
    "Chapitre": 12, "Ligne budgetaire": 18, "Libelle": 52, "Nature": 10,
    "Type": 15, "Montant vote": 20, "N° dossier": 18, "Type prestation": 18,
    "Circuit": 18, "Date demande": 16, "Date decision": 16,
    "Montant demande": 20, "Montant accorde": 20, "Montant paye": 20,
    "Statut": 14, "Motif refus": 28,
    "Mois": 12, "Phase": 18, "Montant": 20,
}


# ---------------------------------------------------------------------------
# Utilitaires
# ---------------------------------------------------------------------------


def _rng(exercice: int, feuille: str) -> random.Random:
    """
    Graine dérivée d'une feuille d'un exercice.

    Chaque feuille tire sur son propre flux : modifier le générateur des
    remboursements ne reboule pas les bénéficiaires, le budget et les
    exécutions — les classeurs déjà importés resteraient alors incohérents
    avec la base.
    """
    return random.Random(f"{GRAINE}:{exercice}:{feuille}")


def _facteur_exercice(exercice: int) -> float:
    """Coefficient d'évolution appliquée aux montants selon l'exercice."""
    return 1.0 + 0.062 * (exercice - EXERCICES[0])


def _date_naissance(rng: random.Random, exercice: int) -> date:
    annee = rng.randint(1952, 2003)
    if annee > exercice - 18:
        annee = exercice - rng.randint(18, 60)
    return date(annee, rng.randint(1, 12), rng.randint(1, 28))


def _date_inscription(rng: random.Random, exercice: int) -> date:
    return date(exercice, rng.randint(1, 12), rng.randint(1, 28))


def _montant_cotisation(rng: random.Random, categorie: str, exercice: int) -> int:
    base = {
        "fonctionnaire": 1_780_000,
        "contractuel": 920_000,
        "retraite": 1_240_000,
    }[categorie]
    bruit = rng.uniform(0.85, 1.18)
    return int(base * bruit * _facteur_exercice(exercice))


def _jours_dans_mois(annee: int, mois: int) -> int:
    if mois == 12:
        return 31
    return (date(annee, mois + 1, 1) - timedelta(days=1)).day


# ---------------------------------------------------------------------------
# Générateurs de feuilles
# ---------------------------------------------------------------------------


def generer_beneficiaires(rng: random.Random, exercice: int) -> list[list]:
    volume = VOLUME_PAR_EXERCICE[exercice]
    lignes: list[list] = []

    for index in range(1, volume + 1):
        pensionne = rng.random() < (0.24 + 0.02 * (exercice - EXERCICES[0]))
        if pensionne:
            categorie = rng.choice(CATEGORIES_PENSIONNE)
            situation = "pensionne"
        else:
            categorie = rng.choice(CATEGORIES_ACTIF)
            situation = "actif"

        genre = rng.choices(("M", "F"), weights=(0.56, 0.44))[0]
        if genre == "M":
            prenom = rng.choice(PRENOMS_HOMMES)
        else:
            prenom = rng.choice(PRENOMS_FEMMES)

        commune = rng.choice(COMMUNES)
        district = (
            "Vatovavy" if commune in ("Vatovavy", "Antanambao", "Tazavato")
            else "Ifanadiana" if commune == "Ifanadiana"
            else "Nosy Varika" if commune == "Nosy Varika"
            else "Mananjary" if commune == "Mananjary"
            else rng.choice(DISTRICTS)
        )

        cin = f"{rng.randint(100_000_000_000, 999_999_999_999)}"
        if rng.random() < 0.03:
            cin = ""

        lignes.append([
            f"RFM-{exercice}-{index:05d}",
            rng.choice(NOMS),
            prenom,
            _date_naissance(rng, exercice).strftime("%d/%m/%Y"),
            genre,
            situation,
            categorie,
            rng.choices(STATUTS_DOSSIER, weights=(0.90, 0.06, 0.04))[0],
            rng.choice(DIRECTIONS),
            "Vatovavy",
            district,
            commune if rng.random() > 0.02 else "",
            cin,
            _montant_cotisation(rng, categorie, exercice),
            _date_inscription(rng, exercice).strftime("%d/%m/%Y"),
            exercice,
        ])

    lignes.append([
        f"RFM-{exercice}-{volume + 1:05d}",
        "RAMAROSON", "Mialy", "07/05/1989", "F", "actif", "contractuel",
        "actif", DIRECTIONS[1], "Vatovavy", "Vatovavy", "Vatovavy",
        "201145678901", "N/A", "15/06/%d" % exercice, exercice,
    ])

    lignes.append(list(lignes[7]))
    lignes[-1][-1] = exercice

    return lignes


def generer_budget(rng: random.Random, exercice: int) -> list[list]:
    lignes: list[list] = []
    facteur = _facteur_exercice(exercice)
    for chapitre, ligne, libelle, type_budget, montant_reference in LIGNES_BUDGETAIRES:
        vote_lfi = int(montant_reference * facteur * rng.uniform(0.97, 1.03))
        vote_lfi = int(round(vote_lfi, -5))
        lignes.append([
            exercice, chapitre, ligne, libelle, "lfi", type_budget, vote_lfi,
        ])
        if rng.random() < 0.55:
            vote_lfr = int(round(vote_lfi * rng.uniform(1.02, 1.08), -5))
            lignes.append([
                exercice, chapitre, ligne, libelle, "lfr", type_budget, vote_lfr,
            ])
    return lignes


def beneficiaires_referencables(
    beneficiaires: list[list],
    exercice: int,
) -> list[list]:
    """
    Bénéficiaires réellement déversés, donc utilisables comme référence.

    Les deux dernières lignes sont volontairement fautives (montant « N/A »
    puis doublon) : elles sont rejetées au validation et ne figureront jamais
    dans `beneficiaires`. Un remboursement qui les citerait serait rejeté au
    déversement pour référence introuvable.
    """
    return beneficiaires[:VOLUME_PAR_EXERCICE[exercice]]


def generer_executions(
    rng: random.Random,
    exercice: int,
    budget: list[list],
) -> list[list]:
    """
    Exécutions mensuelles par phase, pour chaque ligne budgétaire votée.

    Chaque ligne `budget` (exercice, chapitre, ligne, nature, montant) devient
    une série de 12 mois : les phases tardives n'apparaissent qu'à partir de
    leur mois d'ouverture, et leur cumul reste strictement inférieur au vote.
    Le triplet `(exercice, ligne budgetaire, nature)` est ce que le déversement
    utilise pour retrouver `budget_id`.
    """
    lignes: list[list] = []

    for ligne_budget in budget:
        _, _, code_ligne, _, nature, _, vote = ligne_budget
        if not isinstance(vote, int) or vote <= 0:
            continue

        realise = vote * rng.uniform(0.68, 0.96)
        poids = [rng.uniform(0.35, 1.65) for _ in range(12)]
        total_poids = sum(poids)
        mensuel = [realise * poids[i] / total_poids for i in range(12)]

        for mois in range(1, 13):
            for phase in PHASES_EXECUTION:
                if mois < PREMIER_MOIS_PAR_PHASE[phase]:
                    continue
                montant = int(
                    round(mensuel[mois - 1] * COEF_PAR_PHASE[phase], -4)
                )
                if montant <= 0:
                    continue
                lignes.append([
                    exercice,
                    code_ligne,
                    nature,
                    f"{exercice}-{mois:02d}",
                    phase,
                    montant,
                ])

    return lignes


def generer_remboursements(
    rng: random.Random,
    exercice: int,
    beneficiaires: list[list],
) -> list[list]:
    volume = int(VOLUME_PAR_EXERCICE[exercice] * rng.uniform(2.1, 2.4))
    types = list(PRESTATIONS.keys())
    poids = [PRESTATIONS[t][2] for t in types]
    lignes: list[list] = []

    for index in range(1, volume + 1):
        beneficiaire = rng.choice(beneficiaires)
        matricule = beneficiaire[0]
        type_prestation = rng.choices(types, weights=poids)[0]
        minimum, maximum, _ = PRESTATIONS[type_prestation]
        montant_demande = int(rng.uniform(minimum, maximum))

        statut = rng.choices(
            [s for s, _ in STATUTS_PONDERES],
            weights=[p for _, p in STATUTS_PONDERES],
        )[0]

        mois = rng.randint(1, 12)
        jour = rng.randint(1, _jours_dans_mois(exercice, mois))
        date_demande = f"{jour:02d}/{mois:02d}/{exercice}"

        montant_accorde = None
        montant_paye = None
        date_decision = ""
        motif_refus = ""

        if statut in ("paye", "valide"):
            montant_accorde = int(montant_demande * rng.uniform(0.72, 1.0))
        if statut == "paye":
            montant_paye = montant_accorde

        if statut in ("paye", "valide", "refuse"):
            decalage = rng.randint(3, 26)
            jour_decision = jour + decalage
            mois_decision = mois
            while jour_decision > _jours_dans_mois(exercice, mois_decision):
                jour_decision -= _jours_dans_mois(exercice, mois_decision)
                mois_decision += 1
                if mois_decision > 12:
                    mois_decision = 12
                    jour_decision = _jours_dans_mois(exercice, 12)
                    break
            date_decision = f"{jour_decision:02d}/{mois_decision:02d}/{exercice}"

        if statut == "refuse":
            motif_refus = rng.choice([
                "Justificatifs incomplets",
                "Dossier hors delai de(validite",
                "Beneficiaire non identifie",
                "Acte de soins non conforme",
            ])

        lignes.append([
            f"RM-{exercice}-{index:05d}",
            matricule,
            type_prestation,
            rng.choices(
                ("circuit_normal", "circuit_accelere"), weights=(0.82, 0.18)
            )[0],
            date_demande,
            date_decision,
            montant_demande,
            montant_accorde if montant_accorde is not None else "",
            montant_paye if montant_paye is not None else "",
            statut,
            motif_refus,
            exercice,
        ])

    return lignes


# ---------------------------------------------------------------------------
# Écriture du classeur
# ---------------------------------------------------------------------------


def ecrire_feuille(
    classeur: Workbook,
    titre: str,
    entetes: list[str],
    lignes: list[list],
    *,
    colonnes_date: tuple[str, ...] = (),
    colonnes_montant: tuple[str, ...] = (),
    premiere: bool = False,
) -> None:
    feuille = classeur.active if premiere else classeur.create_sheet()
    feuille.title = titre
    feuille.append(entetes)

    for cellule in feuille[1]:
        cellule.font = STYLE_ENTETE_FONT
        cellule.fill = STYLE_ENTETE_FILL
        cellule.alignment = Alignment(horizontal="center", vertical="center")

    index_date = {entetes.index(nom): nom for nom in colonnes_date}
    index_montant = {entetes.index(nom): nom for nom in colonnes_montant}

    for ligne in lignes:
        feuille.append(ligne)

    for index, nom in index_date.items():
        for cellule in feuille.iter_rows(
            min_row=2, min_col=index + 1, max_col=index + 1
        ):
            cellule[0].alignment = Alignment(horizontal="center")
            cellule[0].number_format = "General"

    for index, nom in index_montant.items():
        for cellule in feuille.iter_rows(
            min_row=2, min_col=index + 1, max_col=index + 1
        ):
            cellule[0].number_format = FORMAT_MONTANT
            cellule[0].alignment = Alignment(horizontal="right")

    for index, nom in enumerate(entetes, start=1):
        feuille.column_dimensions[get_column_letter(index)].width = LARGEURS.get(
            nom, 16
        )

    feuille.freeze_panes = "A2"
    feuille.auto_filter.ref = feuille.dimensions


def ecrire_classeur(exercice: int, lignes: dict[str, list[list]]) -> Path:
    classeur = Workbook()

    ecrire_feuille(
        classeur, "Beneficiaires", ENTETES_BENEFICIAIRES,
        lignes["beneficiaires"],
        colonnes_date=("Date de naissance", "Date d'inscription"),
        colonnes_montant=("Montant cotisation",),
        premiere=True,
    )
    ecrire_feuille(
        classeur, "Budget", ENTETES_BUDGET, lignes["budget"],
        colonnes_montant=("Montant vote",),
    )
    ecrire_feuille(
        classeur, "Executions", ENTETES_EXECUTIONS, lignes["executions"],
        colonnes_montant=("Montant",),
    )
    ecrire_feuille(
        classeur, "Remboursements", ENTETES_REMBOURSEMENTS,
        lignes["remboursements"],
        colonnes_date=("Date demande", "Date decision"),
        colonnes_montant=("Montant demande", "Montant accorde", "Montant paye"),
    )

    chemin = DOSSIER_CIBLE / f"RFM_SRB_Exercice_{exercice}.xlsx"
    classeur.save(chemin)
    return chemin


# ---------------------------------------------------------------------------
# Contrôle via le pipeline d'import réel
# ---------------------------------------------------------------------------


#: Types attendus par feuille — un écart signale une colonne que le pipeline
#: d'import classerait autrement (d'où des rejets en cascade).
TYPES_ATTENDUS: dict[str, dict[str, str]] = {
    "Beneficiaires": {
        "matricule": "texte",
        "date_de_naissance": "date",
        "date_d_inscription": "date",
        "montant_cotisation": "montant",
        "exercice": "entier",
    },
    "Budget": {
        "chapitre": "texte",
        "ligne_budgetaire": "texte",
        "nature": "texte",
        "montant_vote": "montant",
        "exercice": "entier",
    },
    "Executions": {
        "ligne_budgetaire": "texte",
        "nature": "texte",
        "mois": "texte",
        "phase": "texte",
        "montant": "montant",
        "exercice": "entier",
    },
    "Remboursements": {
        "n_dossier": "texte",
        "matricule": "texte",
        "date_demande": "date",
        "date_decision": "date",
        "montant_demande": "montant",
        "montant_accorde": "montant",
        "montant_paye": "montant",
        "exercice": "entier",
    },
}


def controler_fichier(chemin: Path) -> dict:
    """Valide chaque feuille avec le vrai pipeline, sans écrire en base."""
    sys.path.insert(0, str(RACINE))
    from app.imports.cibles import cible_pour_feuille
    from app.imports.colonnes import (
        analyser_colonnes,
        lister_feuilles,
        lire_fichier,
    )
    from app.imports.validation import marquer_doublons, valider_lignes

    contenu = chemin.read_bytes()
    titres = lister_feuilles(contenu, chemin.name)
    feuilles: list[dict] = []

    for index, titre in enumerate(titres):
        cible = cible_pour_feuille(titre)
        headers, grille, _ = lire_fichier(contenu, chemin.name, feuille=index)
        colonnes = analyser_colonnes(headers, grille)
        validees = valider_lignes(colonnes, grille, [])
        acceptees = [l for l in validees if l.valide]
        _, doublons = marquer_doublons(acceptees)
        rejets = [m for l in validees if not l.valide for m in l.erreurs]

        types = {c["nom_normalise"]: c["type_detecte"] for c in colonnes}
        attendus = TYPES_ATTENDUS.get(titre, {})
        fautes = [
            f"{nom}={types.get(nom)} (attendu {attendu})"
            for nom, attendu in attendus.items()
            if types.get(nom) != attendu
        ]

        feuilles.append({
            "titre": titre,
            "index": index,
            "cible": cible.cle if cible else None,
            "lignes": len(grille),
            "acceptees": len(acceptees) - len(doublons),
            "rejets": len(rejets),
            "doublons": len(doublons),
            "fautes_types": fautes,
            "motifs": sorted({m["raison"] for m in rejets + doublons}),
        })

    return {"titres": titres, "feuilles": feuilles}


# ---------------------------------------------------------------------------
# Point d'entrée
# ---------------------------------------------------------------------------


def main() -> int:
    global DOSSIER_CIBLE

    analyseur = argparse.ArgumentParser(
        description="Génère les classeurs Excel par exercice (2021-2024)."
    )
    analyseur.add_argument(
        "--dossier", type=Path, default=DOSSIER_CIBLE,
        help="Dossier de destination des fichiers .xlsx.",
    )
    analyseur.add_argument(
        "--sans-controle", action="store_true",
        help="Ne pas exécuter la passe de contrôle via le pipeline d'import.",
    )
    arguments = analyseur.parse_args()

    DOSSIER_CIBLE = arguments.dossier
    DOSSIER_CIBLE.mkdir(parents=True, exist_ok=True)

    echec = 0

    for exercice in EXERCICES:
        beneficiaires = generer_beneficiaires(
            _rng(exercice, "beneficiaires"), exercice
        )
        budget = generer_budget(_rng(exercice, "budget"), exercice)
        lignes = {
            "beneficiaires": beneficiaires,
            "budget": budget,
            "executions": generer_executions(
                _rng(exercice, "executions"), exercice, budget
            ),
            "remboursements": generer_remboursements(
                _rng(exercice, "remboursements"),
                exercice,
                beneficiaires_referencables(beneficiaires, exercice),
            ),
        }
        chemin = ecrire_classeur(exercice, lignes)
        print(
            f"[gen] {chemin.name} : "
            f"{len(lignes['beneficiaires'])} beneficiaires, "
            f"{len(lignes['budget'])} lignes budgetaires, "
            f"{len(lignes['executions'])} executions, "
            f"{len(lignes['remboursements'])} remboursements"
        )

        if arguments.sans_controle:
            continue

        controle = controler_fichier(chemin)
        for feuille in controle["feuilles"]:
            cible = feuille["cible"] or "-"
            print(
                f"       [{feuille['titre']} -> {cible}] "
                f"{feuille['acceptees']} acceptees / {feuille['lignes']}, "
                f"{feuille['rejets']} rejets, {feuille['doublons']} doublons"
            )
            if feuille["fautes_types"]:
                echec = 1
                print(
                    "       !! types incorrects : "
                    + ", ".join(feuille["fautes_types"])
                )
            if feuille["cible"] is None:
                echec = 1
                print("       !! onglet non reconnu pour le déversement")
            for motif in feuille["motifs"]:
                print(f"       motif    : {motif}")

    print(f"[gen] fichiers disponibles dans {DOSSIER_CIBLE}")
    return echec


if __name__ == "__main__":
    raise SystemExit(main())