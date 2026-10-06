"""Normalisation et parsing des types de données."""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

# ---------------------------------------------------------------------------
# Montants
# ---------------------------------------------------------------------------

_SUFFIXES_MONNAIE: list[tuple[str, Decimal]] = [
    ("ARIARY", Decimal(1)),
    ("AR.", Decimal(1)),
    ("AR", Decimal(1)),
    ("MILLIARDS", Decimal("1000000000")),
    ("MILLIONS", Decimal("1000000")),
    ("M", Decimal("1000000")),
    ("K", Decimal("1000")),
]

# ---------------------------------------------------------------------------
# Dates
# ---------------------------------------------------------------------------

FORMATS_DATE: tuple[str, ...] = (
    "%d/%m/%Y",
    "%d-%m-%Y",
    "%d.%m.%Y",
    "%Y-%m-%d",
    "%Y/%m/%d",
    "%d/%m/%y",
    "%d-%m-%y",
    "%d/%m/%Y %H:%M",
)

# ---------------------------------------------------------------------------
# Helpers internes
# ---------------------------------------------------------------------------

_RE_ESPACES = re.compile(r"\s+")


def _separateur_decimal_decimal(valeur: str) -> tuple[str, str]:
    """Détecte les séparateurs de milliers/décimals et renvoie (mille, dec)."""
    if "," in valeur and "." in valeur:
        if valeur.rfind(",") > valeur.rfind("."):
            return (".", ",")
        return (",", ".")
    if "," in valeur:
        partie_ent, _, dec_partie = valeur.rpartition(",")
        if len(dec_partie) == 3 and any(c.isdigit() for c in partie_ent):
            return (",", "")
        return ("", ",")
    if "." in valeur:
        if valeur.count(".") > 1:
            return (".", "")
        partie_ent, _, dec_partie = valeur.rpartition(".")
        if len(dec_partie) == 3 and partie_ent:
            return (".", "")
        return ("", ".")
    return ("", "")


# ---------------------------------------------------------------------------
# Parseurs publics
# ---------------------------------------------------------------------------


def parser_montant(valeur: Any) -> Decimal:
    """Parse un montant ariary depuis des formats courants."""
    if isinstance(valeur, Decimal):
        return valeur
    if isinstance(valeur, bool):
        raise ValueError("booléen non interprétable comme montant")
    if isinstance(valeur, (int, float)):
        return Decimal(str(valeur))
    if isinstance(valeur, datetime):
        raise ValueError("datetime non interprétable comme montant")
    if isinstance(valeur, date):
        raise ValueError("date non interprétable comme montant")
    if not isinstance(valeur, str):
        valeur = str(valeur)

    brut = valeur.strip()
    if not brut:
        raise ValueError("valeur vide")

    multiplicateur = Decimal(1)
    texte_upper = brut.upper()
    for suffixe, mult in _SUFFIXES_MONNAIE:
        if texte_upper.endswith(suffixe):
            multiplicateur = mult
            brut = brut[: -len(suffixe)].strip()
            break

    brut = (
        brut.replace("\u00a0", "")
        .replace("\u202f", "")
        .replace("'", "")
        .replace("\u2019", "")
    )

    signe = ""
    if brut and brut[0] in "+-":
        signe, brut = brut[0], brut[1:]
    brut = brut.strip()

    if not brut:
        raise ValueError("aucun chiffre dans la valeur")

    mille, dec = _separateur_decimal_decimal(brut)

    if mille:
        brut = brut.replace(mille, "")
    if dec and dec != "":
        partie_avant, _, partie_apres = brut.rpartition(dec)
        brut = partie_avant + "." + partie_apres
    elif dec == "":
        pass

    brut = _RE_ESPACES.sub("", brut)
    if not brut:
        raise ValueError("aucun chiffre après nettoyage")

    try:
        return Decimal(brut) * multiplicateur
    except InvalidOperation:
        raise ValueError(f"montant non interprétable : {valeur!r}")


def normaliser_date(valeur: Any) -> date:
    """Parse une date depuis les formats courants (français, ISO)."""
    if isinstance(valeur, datetime):
        return valeur.date()
    if isinstance(valeur, date):
        return valeur
    if not isinstance(valeur, str):
        valeur = str(valeur)

    brut = valeur.strip()
    if not brut:
        raise ValueError("valeur vide")

    for fmt in FORMATS_DATE:
        try:
            return datetime.strptime(brut, fmt).date()
        except ValueError:
            continue

    raise ValueError(f"date non interprétable : {valeur!r}")


def normaliser_entier(valeur: Any) -> int:
    """Parse un entier depuis chaîne ou nombre."""
    if isinstance(valeur, bool):
        raise ValueError("booléen non interprétable comme entier")
    if isinstance(valeur, int):
        return valeur
    if isinstance(valeur, float):
        if valeur == int(valeur):
            return int(valeur)
        raise ValueError(f"flottant non entier : {valeur}")
    if not isinstance(valeur, str):
        valeur = str(valeur)

    brut = (
        valeur.replace(" ", "")
        .replace("\u00a0", "")
        .replace("\u202f", "")
        .strip()
    )
    if not brut:
        raise ValueError("valeur vide")

    try:
        return int(brut)
    except ValueError:
        raise ValueError(f"entier non interprétable : {valeur!r}")


def normaliser_decimal(valeur: Any) -> Decimal:
    """Parse un nombre décimal (taux, ratio) depuis chaîne ou nombre."""
    if isinstance(valeur, Decimal):
        return valeur
    if isinstance(valeur, bool):
        raise ValueError("booléen non interprétable comme décimal")
    if isinstance(valeur, (int, float)):
        return Decimal(str(valeur))
    if not isinstance(valeur, str):
        valeur = str(valeur)

    brut = (
        valeur.replace(" ", "")
        .replace("\u00a0", "")
        .replace("\u202f", "")
        .strip()
    )
    if not brut:
        raise ValueError("valeur vide")

    mille, dec = _separateur_decimal_decimal(brut)
    if mille:
        brut = brut.replace(mille, "")
    if dec and dec != "":
        partie_avant, _, partie_apres = brut.rpartition(dec)
        brut = partie_avant + "." + partie_apres

    try:
        return Decimal(brut)
    except InvalidOperation:
        raise ValueError(f"décimal non interprétable : {valeur!r}")


def normaliser_texte(valeur: Any) -> str | None:
    """Nettoie une valeur texte : trim, collapse espaces, retourne None si vide."""
    if valeur is None:
        return None
    if not isinstance(valeur, str):
        valeur = str(valeur)
    s = valeur.strip().lstrip("\ufeff")
    s = _RE_ESPACES.sub(" ", s)
    return s if s else None


NORMALISATEURS: dict[str, callable] = {
    "texte": normaliser_texte,
    "montant": lambda v: normaliser_texte(v) if normaliser_texte(v) is None else parser_montant(v),
    "date": lambda v: normaliser_texte(v) if normaliser_texte(v) is None else normaliser_date(v),
    "entier": lambda v: normaliser_texte(v) if normaliser_texte(v) is None else normaliser_entier(v),
    "decimal": lambda v: normaliser_texte(v) if normaliser_texte(v) is None else normaliser_decimal(v),
    "vide": lambda v: None,
}