"""Prévision de la consommation mensuelle du budget RFM.

Les séries (Opération : paiement, engagement, …) sont courtes (quelques
exercices). Ce module :
1. analyse la quantité de données temporelles disponibles ;
2. signale explicitement une insuffisance le cas échéant ;
3. applique, en fonction des données, plusieurs modèles : moyenne mobile,
   régression linéaire, régression saisonnière (modèle justifié pour les
   courtes séries mensuelles), ARIMA (statsmodels) et Prophet (si disponible) ;
4. compare les modèles sur un échantillon de validation par des métriques
   adaptées (RMSE, MAE, MAPE) ;
5. produit les prévisions, les intervalles (80 % / 95 %), l'historique, le
   modèle retenu, les métriques et les limites.

Avertissement : avec un ou deux exercices seulement, les résultats sont
présentés comme expérimentaux / indicatifs (qualité « limite » ou
« insuffisante »), jamais comme une certitude.
"""

from __future__ import annotations

import math
import warnings
from typing import Any, Optional

import numpy as np
from sklearn.linear_model import LinearRegression

from app.utils.logging import get_logger

logger = get_logger(__name__)

# --- Identifiants et libellés des modèles ----------------------------------

MODELE_MOYENNE_MOBILE = "moyenne_mobile"
MODELE_REGRESSION_LINEAIRE = "regression_lineaire"
MODELE_REGRESSION_SAISONNIERE = "regression_saisonniere"
MODELE_ARIMA = "arima"
MODELE_PROPHET = "prophet"

MODELES = (
    MODELE_MOYENNE_MOBILE,
    MODELE_REGRESSION_LINEAIRE,
    MODELE_REGRESSION_SAISONNIERE,
    MODELE_ARIMA,
    MODELE_PROPHET,
)

LABELS_MODELES: dict[str, str] = {
    MODELE_MOYENNE_MOBILE: "Moyenne mobile",
    MODELE_REGRESSION_LINEAIRE: "Régression linéaire",
    MODELE_REGRESSION_SAISONNIERE: "Régression saisonnière (tendance + cycle)",
    MODELE_ARIMA: "ARIMA",
    MODELE_PROPHET: "Prophet",
}

DESCRIPTIONS_MODELES: dict[str, str] = {
    MODELE_MOYENNE_MOBILE: (
        "Moyenne glissante sur les 12 derniers mois : référence stable et "
        "facilement interprétable, sans hypothèse de tendance."
    ),
    MODELE_REGRESSION_LINEAIRE: (
        "Tendance linéaire simple (moindres carrés) : pertinente pour une "
        "série presque stable, pas de saisonnalité."
    ),
    MODELE_REGRESSION_SAISONNIERE: (
        "Régression sur tendance + composante saisonnière cyclique (cos/sin). "
        "Adapté aux séries mensuelles courtes (2 ans) : peu de paramètres, "
        "saisonnalité annuelle captée sans sur-apprendre."
    ),
    MODELE_ARIMA: (
        "Créneau ARIMA(p,d,q) choisi par validation sur l'échantillon de "
        "fin de série. Robuste en théorie, mais fiable au-delà d'une "
        "trentaine de points (statsmodels)."
    ),
    MODELE_PROPHET: (
        "Prophet (modèle additif saisonnier) : pertinent à partir de deux "
        "saisons complètes ; dépendance lourde non installée dans cet "
        "environnement."
    ),
}

# --- Paramètres par défaut --------------------------------------------------

MOIS_FENETRE_MOYENNE_MOBILE = 12
DEFAUT_HORIZON = 6  # mois prévus
DEFAUT_TAILLE_TEST = 4  # mois retenus pour la comparaison des modèles

# --- Seuils de suffisance des données ---------------------------------------

MINIMUM_MOIS_INSUFFISANT = 12  # < 12 mois  → insuffisant
MINIMUM_MOIS_SUFFISANT = 36  # ≥ 36 mois  → suffisant ; 12..35 → limite

Z_80 = 1.2816
Z_95 = 1.95996


def mois_suivants(dernier_mois: str, horizon: int) -> list[str]:
    """Renvoie les `horizon` mois ('AAAA-MM') suivant `dernier_mois`."""
    annee, mois = int(dernier_mois[:4]), int(dernier_mois[5:7])
    resultats: list[str] = []
    for _ in range(horizon):
        mois += 1
        if mois > 12:
            mois = 1
            annee += 1
        resultats.append(f"{annee:04d}-{mois:02d}")
    return resultats


def indice_mois(mois: str) -> int:
    return int(mois[5:7]) - 1


# --- Suffisance des données --------------------------------------------------


def evaluer_suffisance(points: int, annees: int) -> dict[str, Any]:
    """Qualifie la quantité de données temporelles disponibles."""
    if points < MINIMUM_MOIS_INSUFFISANT:
        niveau = "insuffisant"
        suffisant = False
        experimental = True
    elif points >= MINIMUM_MOIS_SUFFISANT and annees >= 3:
        niveau = "suffisant"
        suffisant = True
        experimental = False
    else:
        niveau = "limite"
        suffisant = False
        experimental = True

    libelles = {
        "insuffisant": "Données insuffisantes",
        "limite": "Données limitées",
        "suffisant": "Données suffisantes",
    }
    raisons = {
        "insuffisant": (
            f"Seuls {points} point(s) mensuel(s) disponibles (< {MINIMUM_MOIS_INSUFFISANT}) : "
            "aucune prévision robuste possible."
        ),
        "limite": (
            f"{points} points mensuels sur {annees} an(s) : les résultats sont "
            "présentés à titre expérimental / indicatif."
        ),
        "suffisant": (
            f"{points} points mensuels sur {annees} années : prévision possible "
            "avec des réserves habituelles."
        ),
    }
    return {
        "niveau": niveau,
        "libelle": libelles[niveau],
        "suffisant": suffisant,
        "experimental": experimental,
        "raison": raisons[niveau],
        "seuils": {
            "minimum_insuffisant": MINIMUM_MOIS_INSUFFISANT,
            "minimum_suffisant": MINIMUM_MOIS_SUFFISANT,
        },
    }


# --- Métriques d'évaluation ---------------------------------------------------


def metriques(y_reel: np.ndarray, y_predites: np.ndarray) -> dict[str, Any]:
    """RMSE, MAE, MAPE et R² entre valeurs réelles et prévues."""
    y_reel = np.asarray(y_reel, dtype=float)
    y_predites = np.asarray(y_predites, dtype=float)
    erreurs = y_reel - y_predites
    rmse = float(np.sqrt(np.mean(erreurs**2)))
    mae = float(np.mean(np.abs(erreurs)))
    denominateurs = np.abs(y_reel)
    mape = None
    if denominateurs.size and np.all(denominateurs > 0):
        mape = float(np.mean(np.abs(erreurs) / denominateurs) * 100.0)
    moyenne = float(np.mean(y_reel))
    var_tot = float(np.sum((y_reel - moyenne) ** 2))
    r2 = (
        float(1.0 - np.sum(erreurs**2) / var_tot)
        if var_tot > 0
        else None
    )
    return {
        "rmse": round(rmse, 2),
        "mae": round(mae, 2),
        "mape": round(mape, 2) if mape is not None else None,
        "r2": round(r2, 4) if r2 is not None else None,
        "n_test": int(y_reel.size),
    }


# --- Modèles ------------------------------------------------------------------


def _intervalle(base: np.ndarray, sigma: float, largeurs: np.ndarray) -> dict[str, np.ndarray]:
    """Intervalles 80 % / 95 % autour de `base`, `sigma` des résidus."""
    return {
        "bas_80": base - Z_80 * sigma * largeurs,
        "haut_80": base + Z_80 * sigma * largeurs,
        "bas_95": base - Z_95 * sigma * largeurs,
        "haut_95": base + Z_95 * sigma * largeurs,
    }


def _predire_moyenne_mobile(
    valeurs: np.ndarray,
    indices_futurs: np.ndarray,
    fenetre: int,
) -> np.ndarray:
    return np.full(indices_futurs.size, float(np.mean(valeurs[-fenetre:])))


def _predire_lineaire(valeurs: np.ndarray, indices_futurs: np.ndarray) -> np.ndarray:
    t = np.arange(valeurs.size).reshape(-1, 1)
    modele = LinearRegression().fit(t, valeurs)
    return modele.predict(indices_futurs.reshape(-1, 1))


def _features_saisonnieres(indices: np.ndarray) -> np.ndarray:
    """[1, tendance, cos(2π m/12), sin(2π m/12)] pour chaque indice."""
    mois = indices % 12
    angle = 2.0 * math.pi * mois / 12.0
    return np.column_stack(
        [np.ones_like(indices), indices, np.cos(angle), np.sin(angle)]
    )


def _predire_saisonnier(valeurs: np.ndarray, indices_futurs: np.ndarray) -> np.ndarray:
    t = np.arange(valeurs.size)
    modele = LinearRegression().fit(_features_saisonnieres(t), valeurs)
    return modele.predict(_features_saisonnieres(indices_futurs))


def _predire_arima(
    valeurs: np.ndarray,
    pas: int,
    ordre: tuple[int, int, int],
) -> Any:
    """Prévision statsmodel ARIMA (None si indisponible ou en échec)."""
    try:
        from statsmodels.tsa.arima.model import ARIMA as StatsARIMA
    except ImportError:
        return None

    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=UserWarning)
        try:
            resultat = StatsARIMA(valeurs, order=ordre).fit()
        except Exception as erreur:  # noqa: BLE001 — modèle non convergé
            logger.debug("ARIMA %s échec : %s", ordre, erreur)
            return None
    try:
        prevision = resultat.get_forecast(steps=pas)
        return {
            "moyennes": np.asarray(prevision.predicted_mean, dtype=float),
            "residus": np.asarray(resultat.resid, dtype=float),
        }
    except Exception:  # noqa: BLE001
        return None


def _selectionner_arima(valeurs: np.ndarray, test_size: int) -> tuple[Optional[tuple[int, int, int]], dict[str, Any]]:
    """Choisit (p, d, q) par RMSE sur l'échantillon de validation."""
    if valeurs.size < (3 + test_size):
        return None, {}
    entrainement = valeurs[:-test_size]
    reel = valeurs[-test_size:]
    meilleur: Optional[tuple[int, int, int]] = None
    meilleur_rmse: float | None = None
    detail: dict[str, dict[str, Any]] = {}
    for p in range(3):
        for d in range(2):
            for q in range(3):
                if p == 0 and d == 0 and q == 0:
                    continue
                ordre = (p, d, q)
                prevision = _predire_arima(entrainement, test_size, ordre)
                if prevision is None:
                    continue
                rmse = float(np.sqrt(np.mean((reel - prevision["moyennes"]) ** 2)))
                detail[str(ordre)] = {"ordre": ordre, "rmse": round(rmse, 2)}
                if meilleur_rmse is None or rmse < meilleur_rmse:
                    meilleur_rmse = rmse
                    meilleur = ordre
    return meilleur, detail


# --- Fonction principale -------------------------------------------------------


def generer_forecast(
    mois: list[str],
    valeurs: list[float],
    horizon: int = DEFAUT_HORIZON,
    test_size: int = DEFAUT_TAILLE_TEST,
    methode: Optional[str] = None,
    fenetre_moyenne_mobile: int = MOIS_FENETRE_MOYENNE_MOBILE,
) -> dict[str, Any]:
    """Produit la prévision complète (modèles, métriques, intervalles, limites).

    `methode` restreint éventuellement la comparaison à un seul modèle.
    """
    mois = list(mois)
    valeurs_arr = np.asarray(valeurs, dtype=float)
    points = int(valeurs_arr.size)
    annees = len({int(m[:4]) for m in mois}) if points else 0
    dernier_mois = mois[-1] if mois else None
    suffisance = evaluer_suffisance(points, annees)

    modeles_a_tester = [methode] if methode in MODELES else list(MODELES)

    resultats: list[dict[str, Any]] = []
    for cle in modeles_a_tester:
        resultat = _tester_modele(
            cle,
            mois,
            valeurs_arr,
            horizon=horizon,
            test_size=test_size,
            fenetre=fenetre_moyenne_mobile,
            suffisant=suffisance["suffisant"],
        )
        resultat["label"] = LABELS_MODELES[cle]
        resultat["description"] = DESCRIPTIONS_MODELES[cle]
        resultats.append(resultat)

    # Classement par métrique (RMSE), modèles appliqués uniquement.
    appliques = [r for r in resultats if r["applique"] and r.get("metriques")]
    meilleur = None
    if appliques and (methode is None or methode in MODELES):
        meilleur_cles = sorted(
            appliques, key=lambda r: (r["metriques"]["rmse"], r["metriques"]["mae"])
        )
        meilleur = meilleur_cles[0]["cle"]
        for r in resultats:
            r["meilleur"] = r["cle"] == meilleur

    limites = _limites(
        suffisance, points, annees, horizon, dernier_mois, appliques
    )

    return {
        "calcule_le": None,  # rempli par le service avec l'horodatage
        "horizon": horizon,
        "test_size": test_size,
        "points_mensuels": points,
        "exercices": sorted({int(m[:4]) for m in mois}) if mois else [],
        "dernier_mois": dernier_mois,
        "suffisance": suffisance,
        "modeles_essayes": [
            {
                "cle": cle,
                "label": LABELS_MODELES[cle],
                "applique": bool(r["applique"]),
                "raison": r["raison"],
            }
            for cle, r in zip(modeles_a_tester, resultats)
        ],
        "metriques": [
            {
                "modele": r["cle"],
                "label": r["label"],
                "meilleur": bool(r.get("meilleur", False)),
                **r["metriques"],
            }
            for r in resultats
            if r.get("metriques")
        ],
        "selection_arima": None,
        "previsions": [
            {
                "modele": r["cle"],
                "label": r["label"],
                "description": r["description"],
                "applique": r["applique"],
                "raison": r["raison"],
                "meilleur": bool(r.get("meilleur", False)),
                "sigma_residus": r["sigma_residus"] if r["applique"] else None,
                "arima_selection": r.get("arima_selection"),
                "valeurs": r["valeurs"],
            }
            for r in resultats
        ],
        "limites": limites,
        "interpretation": _interpretation(meilleur, suffisance, points),
    }


def _tester_modele(
    cle: str,
    mois: list[str],
    valeurs: np.ndarray,
    horizon: int,
    test_size: int,
    fenetre: int,
    suffisant: bool,
) -> dict[str, Any]:
    """Applique un modèle, mesure sa qualité sur l'échantillon de validation."""
    points = valeurs.size
    if points < 6:
        return {
            "cle": cle,
            "applique": False,
            "raison": "trop peu de points pour évaluer un modèle.",
            "sigma_residus": None,
            "metriques": None,
            "valeurs": [],
            "meilleur": False,
        }

    entrainement = valeurs[:-test_size] if points > test_size else valeurs
    reel = valeurs[-test_size:] if points > test_size else np.array([])

    if cle == MODELE_MOYENNE_MOBILE:
        fenetre_utilisee = min(fenetre, max(1, entrainement.size))
        if entrainement.size < fenetre_utilisee:
            return _inapplique(cle, "fenêtre de moyenne supérieure à l'échantillon.")
        baseline = _predire_moyenne_mobile(entrainement, np.arange(test_size), fenetre_utilisee)
        # Prévision finale : moyenne des 12 derniers mois observés, stable.
        base = _predire_moyenne_mobile(valeurs, np.arange(horizon), fenetre_utilisee)
        sigma = float(np.std(valeurs - np.full(valeurs.size, base[0])))
        largeurs = np.sqrt(np.arange(1, horizon + 1))
        intervals = _intervalle(base, sigma, largeurs)
    elif cle == MODELE_REGRESSION_LINEAIRE:
        if entrainement.size < 4:
            return _inapplique(cle, "échantillon trop court pour une tendance fiable.")
        base = _predire_lineaire(valeurs, np.arange(points, points + horizon))
        predictees = _predire_lineaire(entrainement, np.arange(points - test_size, points))
        sigma = float(np.std(reel - predictees)) if reel.size else float(np.std(valeurs))
        largeurs = np.sqrt(np.arange(1, horizon + 1))
        intervals = _intervalle(base, sigma, largeurs)
    elif cle == MODELE_REGRESSION_SAISONNIERE:
        if entrainement.size < 8:
            return _inapplique(cle, "échantillon trop court pour modéliser la saisonnalité.")
        base = _predire_saisonnier(valeurs, np.arange(points, points + horizon))
        predictees = _predire_saisonnier(entrainement, np.arange(points - test_size, points))
        sigma = float(np.std(reel - predictees)) if reel.size else float(np.std(valeurs))
        largeurs = np.sqrt(np.arange(1, horizon + 1))
        intervals = _intervalle(base, sigma, largeurs)
    elif cle == MODELE_ARIMA:
        ordre, selection = _selectionner_arima(valeurs, test_size)
        if ordre is None:
            return {
                "cle": cle,
                "applique": False,
                "raison": "statsmodels indisponible ou aucun ordre ARIMA n'a convergé.",
                "sigma_residus": None,
                "metriques": None,
                "valeurs": [],
                "meilleur": False,
            }
        # Métriques sur l'échantillon de validation : prévision multi-pas ARIMA
        # calculée à partir de l'entraînement seul.
        metr = None
        test_prevu = None
        if reel.size:
            validation = _predire_arima(entrainement, test_size, ordre)
            if validation is not None:
                test_prevu = [round(float(x), 2) for x in validation["moyennes"]]
                metr = metriques(reel, validation["moyennes"])
        prevision = _predire_arima(valeurs, horizon, ordre)
        if prevision is None:
            return _inapplique(cle, "ARIMA n'a pas convergé sur l'historique complet.")
        base = prevision["moyennes"]
        sigma = (
            float(np.std(prevision["residus"])) if prevision["residus"].size else None
        )
        # Extraction des intervalles via statsmodels (95 %), 80 % proportionnelle.
        try:
            from statsmodels.tsa.arima.model import ARIMA as StatsARIMA

            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", category=UserWarning)
                refaite = StatsARIMA(valeurs, order=ordre).fit()
                borne95 = refaite.get_forecast(steps=horizon).conf_int(alpha=0.05)
                borne80 = refaite.get_forecast(steps=horizon).conf_int(alpha=0.2)
            intervals = {
                "bas_80": np.asarray(borne80[:, 0], dtype=float),
                "haut_80": np.asarray(borne80[:, 1], dtype=float),
                "bas_95": np.asarray(borne95[:, 0], dtype=float),
                "haut_95": np.asarray(borne95[:, 1], dtype=float),
            }
        except Exception:  # noqa: BLE001 — repli sur les résidus
            if sigma is None:
                sigma = float(np.std(valeurs))
            intervals = _intervalle(base, sigma, np.sqrt(np.arange(1, horizon + 1)))
        # _selectionner_arima renvoie le détail de la grille dans `selection`.
        return {
            "cle": cle,
            "applique": True,
            "raison": None,
            "sigma_residus": round(sigma, 2) if sigma is not None else None,
            "metriques": metr,
            "arima_selection": {"ordre": list(ordre), "grille": selection},
            "valeurs": _packer_valeurs(mois, base, intervals),
            "meilleur": False,
            "test_reel": [round(float(x), 2) for x in reel],
            "test_prevu": test_prevu,
        }
    elif cle == MODELE_PROPHET:
        return _inapplique(
            cle,
            "Prophet non pertinent ici : dépendance lourde absente, et deux "
            "années suffisent à peine à deux saisons (la régression saisonnière "
            "est privilégiée).",
        )
    else:
        return _inapplique(cle, "modèle inconnu.")

    # Pour tous les modèles « simples » : métriques sur l'échantillon de
    # validation, à partir de l'entraînement uniquement.
    if reel.size:
        predictees = _predire_validation(cle, entrainement, reel.size, fenetre)
        metr = metriques(reel, predictees)
    else:
        metr = None

    retour = {
        "cle": cle,
        "applique": True,
        "raison": None,
        "sigma_residus": round(float(np.std(_residus_echantillons(valeurs, base, cle, fenetre))), 2),
        "metriques": metr,
        "valeurs": _packer_valeurs(mois, base, intervals),
        "meilleur": False,
        "test_reel": reel.tolist(),
        "test_prevu": predictees.tolist() if reel.size else None,
    }
    return retour


def _predire_validation(
    cle: str,
    entrainement: np.ndarray,
    pas: int,
    fenetre: int,
) -> np.ndarray:
    """Prévision d'évaluation (multi-pas) à partir de l'entraînement seul."""
    indices = np.arange(entrainement.size, entrainement.size + pas)
    if cle == MODELE_MOYENNE_MOBILE:
        return _predire_moyenne_mobile(entrainement, indices, min(fenetre, entrainement.size))
    if cle == MODELE_REGRESSION_LINEAIRE:
        return _predire_lineaire(entrainement, indices)
    if cle == MODELE_REGRESSION_SAISONNIERE:
        return _predire_saisonnier(entrainement, indices)
    return _predire_moyenne_mobile(entrainement, indices, min(fenetre, entrainement.size))


def _residus_echantillons(
    valeurs: np.ndarray,
    base: np.ndarray,
    cle: str,
    fenetre: int,
) -> np.ndarray:
    """Résidus in-sample du modèle simple (pour l'amplitude des intervalles)."""
    indices = np.arange(valeurs.size)
    if cle == MODELE_MOYENNE_MOBILE:
        predites = np.array([
            float(np.mean(valeurs[max(0, i - fenetre):i])) if i > 0 else valeurs[0]
            for i in indices
        ])
    elif cle == MODELE_REGRESSION_LINEAIRE:
        modele = LinearRegression().fit(indices.reshape(-1, 1), valeurs)
        predites = modele.predict(indices.reshape(-1, 1))
    elif cle == MODELE_REGRESSION_SAISONNIERE:
        modele = LinearRegression().fit(_features_saisonnieres(indices), valeurs)
        predites = modele.predict(_features_saisonnieres(indices))
    else:
        predites = np.full(valeurs.size, float(np.mean(valeurs[-fenetre:])))
    return valeurs - predites


def _packer_valeurs(
    mois: list[str],
    base: np.ndarray,
    intervals: dict[str, np.ndarray],
) -> list[dict[str, Any]]:
    """Construit la liste sérialisable des points prévus (avec intervalles)."""
    futurs = mois_suivants(mois[-1], int(base.size)) if mois else []
    return [
        {
            "mois": futurs[i],
            "valeur": round(float(base[i]), 2),
            "bas_80": round(float(intervals["bas_80"][i]), 2),
            "haut_80": round(float(intervals["haut_80"][i]), 2),
            "bas_95": round(float(intervals["bas_95"][i]), 2),
            "haut_95": round(float(intervals["haut_95"][i]), 2),
        }
        for i in range(int(base.size))
    ]


def _inapplique(cle: str, raison: str) -> dict[str, Any]:
    return {
        "cle": cle,
        "applique": False,
        "raison": raison,
        "sigma_residus": None,
        "metriques": None,
        "valeurs": [],
        "meilleur": False,
    }


def _limites(
    suffisance: dict[str, Any],
    points: int,
    annees: int,
    horizon: int,
    dernier_mois: str,
    appliques: list[dict[str, Any]],
) -> list[str]:
    limites: list[str] = []
    if not suffisance["suffisant"]:
        limites.append(
            suffisance["raison"]
            + " Les prévisions sont expérimentales et ne doivent pas être "
            "utilisées seules pour une décision."
        )
    else:
        limites.append("Historique suffisant (données mensuelles et pluriannuelles).")
    if annees < 2:
        limites.append(
            "Moins de deux exercices complets : la saisonnalité annuelle n'est "
            "pas fiablement identifiable."
        )
    if horizon > points:
        limites.append(
            f"L'horizon ({horizon} mois) dépasse la profondeur de l'historique "
            f"({points} mois) : la confiance décroît fortement."
        )
    limites.append(
        "Le modèle ne connaît pas les facteurs de gestion (LFI/LFR, politiques "
        "d'exécution, événements exceptionnels) qui peuvent décaler la consommation."
    )
    if dernier_mois:
        limites.append(
            f"Prévisions générées à partir du dernier mois observé : {dernier_mois}."
        )
    if len(appliques) < 3:
        limites.append(
            "Peu de modèles comparables : la sélection du « meilleur » modèle "
            "reste fragile sur une courte série."
        )
    return limites


def _interpretation(meilleur: Optional[str], suffisance: dict[str, Any], points: int) -> str:
    if points < MINIMUM_MOIS_INSUFFISANT:
        return (
            "Données insuffisantes : aucune prévision exploitable n'est produite. "
            "Enrichir l'historique mensuel avant d'utiliser ce module."
        )
    if meilleur is None:
        return (
            "Aucun modèle n'a pu être appliqué sur la série fournie. "
            "Vérifier la disponibilité des données d'exécution mensuelles."
        )
    label = LABELS_MODELES[meilleur]
    if not suffisance["suffisant"]:
        return (
            f"Résultats expérimentaux / indicatifs : le modèle « {label} » est "
            "le moins mauvais sur la fenêtre de validation, mais l'historique "
            "court impose la prudence."
        )
    return (
        f"Modèle retenu : « {label} », choisi sur la fenêtre de validation par "
        "RMSE puis MAE."
    )