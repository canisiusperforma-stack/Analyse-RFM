"""Validation et nettoyage de chaque ligne de données."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.imports.normalisation import NORMALISATEURS


@dataclass
class LigneValidee:
    """Résultat de validation d'une ligne : valeurs nettoyées + erreurs."""

    numero: int
    valeurs: dict[str, Any]
    manquantes: list[str] = field(default_factory=list)
    erreurs: list[dict] = field(default_factory=list)

    @property
    def valide(self) -> bool:
        return not self.erreurs


def _valeur_manquante(valeur: Any) -> bool:
    return valeur is None or (
        isinstance(valeur, str) and valeur.strip() == ""
    )


def _representer(valeur: Any) -> str:
    if valeur is None:
        return ""
    return str(valeur)


def valider_lignes(
    colonnes: list[dict],
    grille: list[list[Any]],
    colonnes_obligatoires: list[str],
) -> list[LigneValidee]:
    """
    Valide et normalise chaque ligne de la grille.

    - Retourne une LigneValidee par ligne (numéro 1-based dans la grille).
    - Les valeurs vides sont comptées comme manquantes (jamais remplacées).
    - Une erreur de type ou une valeur obligatoire manquante rend la ligne
      invalide, sans jamais modifier la valeur brute d'origine.
    """
    lignes_validees: list[LigneValidee] = []
    nb_colonnes = len(colonnes)

    for index_ligne, brut in enumerate(grille, start=1):
        if all(x is None for x in brut):
            continue

        valeurs: dict[str, Any] = {}
        manquantes: list[str] = []
        erreurs: list[dict] = []

        for idx_col in range(nb_colonnes):
            spec = colonnes[idx_col]
            nom = spec["nom_normalise"]
            type_colonne = spec["type_detecte"]
            brut_val = brut[idx_col] if idx_col < len(brut) else None

            if _valeur_manquante(brut_val):
                manquantes.append(nom)
                if nom in colonnes_obligatoires:
                    erreurs.append({
                        "ligne": index_ligne,
                        "colonne": nom,
                        "valeur": _representer(brut_val),
                        "raison": f"Valeur obligatoire manquante ({nom})",
                        "type_erreur": "obligatoire",
                    })
                continue

            normalisateur = NORMALISATEURS[type_colonne]
            try:
                valeur_normalisee = normalisateur(brut_val)
                if valeur_normalisee is None:
                    manquantes.append(nom)
                    continue
                valeurs[nom] = valeur_normalisee
            except ValueError as e:
                erreurs.append({
                    "ligne": index_ligne,
                    "colonne": nom,
                    "valeur": _representer(brut_val),
                    "raison": str(e),
                    "type_erreur": "type",
                })

        lignes_validees.append(
            LigneValidee(
                numero=index_ligne,
                valeurs=valeurs,
                manquantes=manquantes,
                erreurs=erreurs,
            )
        )

    return lignes_validees


def marquer_doublons(
    lignes_validees: list[LigneValidee],
) -> tuple[list[LigneValidee], list[dict]]:
    """
    Détecte les doublons parmi les lignes valides (sur les valeurs nettoyées).

    Renvoie (lignes_gardées, rejets_doublons).
    La première occurrence est conservée ; les suivantes sont rejetées avec
    un motif explicite référençant la ligne d'origine dupliquée.
    """
    vues: dict[tuple, int] = {}
    gardees: list[LigneValidee] = []
    rejets: list[dict] = []

    for lv in lignes_validees:

        cle = tuple(sorted(
            (k, repr(v)) for k, v in lv.valeurs.items()
        ))
        premiere = vues.get(cle)
        if premiere is not None:
            rejets.append({
                "ligne": lv.numero,
                "colonne": "*",
                "valeur": f"ligne {premiere}",
                "raison": (
                    f"Doublon de la ligne {premiere} "
                    "(valeurs identiques après normalisation)"
                ),
                "type_erreur": "doublon",
            })
            continue

        vues[cle] = lv.numero
        gardees.append(lv)

    return gardees, rejets