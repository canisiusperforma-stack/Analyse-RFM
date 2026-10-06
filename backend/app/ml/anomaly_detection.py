"""Détection d'observations atypiques dans les séries de remboursements.

Le module implémente quatre méthodes complémentaires et produit, pour
chaque observation signalée, un score, un niveau et une justification
lisible.

Méthodes (testées selon la nature des données disponibles) :
- `iqr`              : intervalle interquartile (robuste aux asymétries) ;
- `zscore`           : écart réduit, fondé sur la moyenne et l'écart-type ;
- `isolation_forest` : apprentissage non supervisé (scikit-learn) ;
- `lof`              : facteur d'anomalie local (densité locale,
  scikit-learn) — utilisé lorsqu'un volume de données suffisant le permet.

Lorsqu'une méthode ne peut pas être appliquée (échantillon trop petit,
variance nulle, données insuffisamment diversifiées), la raison est
renvoyée dans le rapport au lieu d'un faux résultat.

Précautions sémantiques (exigence métier) :
- aucune observation n'est **jamais** qualifiée automatiquement de fraude ;
- seul le lexique suivant est utilisé :
  * « observation atypique »  (1 méthode signalante) ;
  * « anomalie potentielle »  (2 méthodes signalantes) ;
  * « valeur à vérifier »     (3 méthodes signalantes ou plus) ;
- chaque alerte porte une justification lisible et un statut de
  vérification qui commence toujours à « à vérifier ».
"""

from __future__ import annotations

from typing import Any, Callable, Optional

import numpy as np

METHODES = ("iqr", "zscore", "isolation_forest", "lof")

LABELS_METHODES = {
    "iqr": "Intervalle interquartile (IQR)",
    "zscore": "Écart réduit (z-score)",
    "isolation_forest": "Forêt d'isolation (Isolation Forest)",
    "lof": "Facteur d'anomalie local (LOF)",
}

MINIMUM_OBSERVATIONS = {
    "iqr": 4,
    "zscore": 3,
    "isolation_forest": 12,
    "lof": 20,
}

# Niveau attribué selon le nombre de méthodes indépendantes qui signalent.
NIVEAU_1_METHODE = "observation_atypique"
NIVEAU_2_METHODES = "anomalie_potentielle"
NIVEAU_3_METHODES = "valeur_a_verifier"

LABELS_NIVEAUX = {
    NIVEAU_1_METHODE: "observation atypique",
    NIVEAU_2_METHODES: "anomalie potentielle",
    NIVEAU_3_METHODES: "valeur à vérifier",
}

# Niveaux ordonnés du signal le plus faible au plus fort.
NIVEAUX = (NIVEAU_1_METHODE, NIVEAU_2_METHODES, NIVEAU_3_METHODES)

PARAMETRES_PAR_DEFAUT = {
    "iqr": {"facteur": 1.5},
    "zscore": {"seuil": 3.0},
    "isolation_forest": {"contamination": 0.05, "graine": 42, "n_estimateurs": 100},
    "lof": {"contamination": 0.05, "voisins": None},
}


def niveau_pour(nombre_methodes: int) -> str:
    """Niveau associé au nombre de méthodes signalantes (plafonné à 3)."""
    if nombre_methodes >= 3:
        return NIVEAU_3_METHODES
    if nombre_methodes == 2:
        return NIVEAU_2_METHODES
    return NIVEAU_1_METHODE


def preparer_valeurs(valeurs: Any) -> Optional[np.ndarray]:
    """Convertit une séquence en tableau numpy flottant, sans valeurs manquantes."""
    propres: list[float] = []
    for valeur in valeurs:
        if valeur is None:
            continue
        try:
            nombre = float(valeur)
        except (TypeError, ValueError):
            continue
        if np.isnan(nombre) or np.isinf(nombre):
            continue
        propres.append(nombre)
    if not propres:
        return None
    return np.asarray(propres, dtype=float)


def _normaliser(score_brut: float, plafond: float) -> float:
    """Mappe un score brut sur l'intervalle [0 ; 1] (plafonné)."""
    if not plafond or plafond <= 0:
        return 0.0
    return round(min(float(score_brut), plafond) / plafond, 4)


def _format_francais(valeur: float) -> str:
    """Formatage par défaut des valeurs (séparateur de milliers en espace)."""
    return f"{float(valeur):,.2f}".replace(",", " ").replace(".", ",")


def detecter_avec_iqr(
    arr: np.ndarray,
    facteur: float = 1.5,
) -> dict[str, Any]:
    """Détection par intervalle interquartile (bornes Q1−f·IQR / Q3+f·IQR)."""
    rapport: dict[str, Any] = {
        "appliquee": False,
        "raison": None,
        "donnees": {"facteur": facteur},
        "resultats": [],
    }
    if arr is None or arr.size < MINIMUM_OBSERVATIONS["iqr"]:
        rapport["raison"] = "échantillon trop petit"
        return rapport
    if np.unique(arr).size < 2:
        rapport["raison"] = "valeurs toutes identiques"
        return rapport

    q1, q3 = [float(v) for v in np.percentile(arr, [25, 75])]
    ecart_interquartile = q3 - q1
    if ecart_interquartile <= 1e-9:
        rapport["raison"] = "écart interquartile nul"
        return rapport

    borne_basse = q1 - facteur * ecart_interquartile
    borne_haute = q3 + facteur * ecart_interquartile
    rapport["appliquee"] = True
    rapport["donnees"].update({
        "q1": _format_francais(q1),
        "q3": _format_francais(q3),
        "borne_basse": _format_francais(borne_basse),
        "borne_haute": _format_francais(borne_haute),
        "ecart_interquartile": _format_francais(ecart_interquartile),
    })

    resultats = []
    for indice, valeur in enumerate(arr):
        valeur_float = float(valeur)
        if valeur_float < borne_basse:
            distance = (borne_basse - valeur_float) / ecart_interquartile
            resultats.append({
                "indice": indice,
                "score": _normaliser(distance, 5.0),
                "score_brut": round(distance, 4),
                "detectee": True,
                "details": {
                    "cote": "inferieure",
                    "borne": borne_basse,
                    "distance_iqr": round(distance, 2),
                },
            })
        elif valeur_float > borne_haute:
            distance = (valeur_float - borne_haute) / ecart_interquartile
            resultats.append({
                "indice": indice,
                "score": _normaliser(distance, 5.0),
                "score_brut": round(distance, 4),
                "detectee": True,
                "details": {
                    "cote": "superieure",
                    "borne": borne_haute,
                    "distance_iqr": round(distance, 2),
                },
            })
        else:
            resultats.append({
                "indice": indice,
                "score": 0.0,
                "score_brut": 0.0,
                "detectee": False,
                "details": None,
            })
    rapport["resultats"] = resultats
    return rapport


def detecter_avec_zscore(
    arr: np.ndarray,
    seuil: float = 3.0,
) -> dict[str, Any]:
    """Détection par écart réduit : |x − moyenne| / écart-type ≥ seuil."""
    rapport: dict[str, Any] = {
        "appliquee": False,
        "raison": None,
        "donnees": {"seuil": seuil},
        "resultats": [],
    }
    if arr is None or arr.size < MINIMUM_OBSERVATIONS["zscore"]:
        rapport["raison"] = "échantillon trop petit"
        return rapport

    moyenne = float(arr.mean())
    ecart_type = float(arr.std(ddof=1)) if arr.size > 1 else 0.0
    if ecart_type <= 1e-9:
        rapport["raison"] = "variance nulle (valeurs identiques)"
        return rapport

    rapport["appliquee"] = True
    rapport["donnees"].update({
        "moyenne": _format_francais(moyenne),
        "ecart_type": _format_francais(ecart_type),
    })

    resultats = []
    for indice, valeur in enumerate(arr):
        zscore = (float(valeur) - moyenne) / ecart_type
        valeur_absolue = abs(zscore)
        resultats.append({
            "indice": indice,
            "score": _normaliser(valeur_absolue, 10.0),
            "score_brut": round(valeur_absolue, 4),
            "detectee": valeur_absolue >= seuil,
            "details": {
                "zscore": round(zscore, 3),
                "moyenne": moyenne,
                "ecart_type": ecart_type,
            },
        })
    rapport["resultats"] = resultats
    return rapport


def detecter_avec_isolation_forest(
    arr: np.ndarray,
    contamination: float = 0.05,
    graine: int = 42,
    n_estimateurs: int = 100,
) -> dict[str, Any]:
    """Détection par isolation forest (scikit-learn), variable unidimensionnelle."""
    rapport: dict[str, Any] = {
        "appliquee": False,
        "raison": None,
        "donnees": {
            "contamination": contamination,
            "graine": graine,
            "n_estimateurs": n_estimateurs,
        },
        "resultats": [],
    }
    if arr is None or arr.size < MINIMUM_OBSERVATIONS["isolation_forest"]:
        rapport["raison"] = "échantillon trop petit"
        return rapport
    if np.unique(arr).size < 3:
        rapport["raison"] = "valeurs insuffisamment diversifiées"
        return rapport
    if not 0.0 < contamination < 0.5:
        rapport["raison"] = "contamination hors bornes (0 ; 0,5)"
        return rapport

    try:
        from sklearn.ensemble import IsolationForest
    except ImportError:
        rapport["raison"] = "scikit-learn indisponible"
        return rapport

    x = arr.reshape(-1, 1)
    try:
        modele = IsolationForest(
            n_estimators=int(n_estimateurs),
            contamination=contamination,
            random_state=int(graine),
            n_jobs=1,
        )
        modele.fit(x)
    except Exception as erreur:  # noqa: BLE001 — la méthode est simplement non applicable
        rapport["raison"] = f"échec d'entraînement : {erreur}"
        return rapport

    predictions = modele.predict(x)
    scores = -modele.score_samples(x)
    if np.ptp(scores) > 1e-9:
        scores_normalises = (scores - scores.min()) / (scores.max() - scores.min())
    else:
        scores_normalises = np.zeros_like(scores)

    rapport["appliquee"] = True
    resultats = []
    for indice in range(arr.size):
        detectee = bool(predictions[indice] == -1)
        resultats.append({
            "indice": indice,
            "score": round(float(scores_normalises[indice]), 4),
            "score_brut": round(float(-scores[indice]), 4),
            "detectee": detectee,
            "details": {
                "score_echantillon": round(float(scores[indice]), 4),
                "contamination": contamination,
            },
        })
    rapport["resultats"] = resultats
    return rapport


def detecter_avec_lof(
    arr: np.ndarray,
    contamination: float = 0.05,
    voisins: Optional[int] = None,
) -> dict[str, Any]:
    """Détection par facteur d'anomalie local (LOF), densité locale."""
    rapport: dict[str, Any] = {
        "appliquee": False,
        "raison": None,
        "donnees": {"contamination": contamination, "voisins": voisins},
        "resultats": [],
    }
    if arr is None or arr.size < MINIMUM_OBSERVATIONS["lof"]:
        rapport["raison"] = "échantillon trop petit (LOF peu fiable en petit volume)"
        return rapport
    if np.unique(arr).size < 4:
        rapport["raison"] = "valeurs insuffisamment diversifiées"
        return rapport
    if not 0.0 < contamination < 0.5:
        rapport["raison"] = "contamination hors bornes (0 ; 0,5)"
        return rapport

    nombre = arr.size
    voisins_max = (nombre // 2) - 1
    k = min(int(voisins) if voisins and int(voisins) > 0 else 20, voisins_max)
    if k < 2:
        rapport["raison"] = "trop peu de voisins possibles"
        return rapport

    try:
        from sklearn.neighbors import LocalOutlierFactor
    except ImportError:
        rapport["raison"] = "scikit-learn indisponible"
        return rapport

    x = arr.reshape(-1, 1)
    try:
        import warnings as _warnings

        modele = LocalOutlierFactor(
            n_neighbors=k,
            contamination=contamination,
            metric="minkowski",
            n_jobs=1,
        )
        with _warnings.catch_warnings():
            # Sklearn signale des doublons (inévitables ici) sans rendre le
            # calcul inutilisable ; on évite un log d'avertissement à chaque run.
            _warnings.filterwarnings(
                "ignore",
                message="Duplicate values are leading to incorrect results.*",
                category=UserWarning,
            )
            predictions = modele.fit_predict(x)
            facteurs = -modele.negative_outlier_factor_
    except Exception as erreur:  # noqa: BLE001 — la méthode est simplement non applicable
        rapport["raison"] = f"échec du calcul : {erreur}"
        return rapport

    rapport["appliquee"] = True
    rapport["donnees"]["voisins_effectifs"] = k
    resultats = []
    for indice in range(arr.size):
        detectee = bool(predictions[indice] == -1)
        resultats.append({
            "indice": indice,
            "score": _normaliser(float(facteurs[indice]), 4.0),
            "score_brut": round(float(facteurs[indice]), 4),
            "detectee": detectee,
            "details": {
                "facteur_lof": round(float(facteurs[indice]), 3),
                "voisins": k,
                "contamination": contamination,
            },
        })
    rapport["resultats"] = resultats
    return rapport


def _justifier_methode(
    methode: str,
    label: str,
    details: Optional[dict[str, Any]],
    valeur: float,
    formater_valeur: Callable[[float], str],
) -> str:
    """Construit une justification lisible pour une méthode donnée."""
    if details is None:
        return f"{label} : pas de signal."

    if methode == "iqr":
        sens = (
            "dépasse la borne supérieure"
            if details.get("cote") == "superieure"
            else "se situe sous la borne inférieure"
        )
        return (
            f"{label} : valeur {formater_valeur(valeur)} {sens} "
            f"de {details['distance_iqr']:.1f} × l'écart interquartile "
            f"(borne à {_format_francais(details['borne'])})."
        )
    if methode == "zscore":
        ecart_type = details.get("ecart_type") or 0.0
        return (
            f"{label} : écart réduit de {abs(details['zscore']):.3f} "
            f"(seuil 3,0 ; écart-type {_format_francais(ecart_type)}) "
            f"par rapport à la moyenne {_format_francais(details['moyenne'])}."
        )
    if methode == "isolation_forest":
        return (
            f"{label} : score d'isolation de "
            f"{abs(details['score_echantillon']):.3f} (contamination "
            f"{float(details['contamination']) * 100:.0f} %)."
        )
    if methode == "lof":
        return (
            f"{label} : facteur local de {details['facteur_lof']:.2f} "
            f"(densité atypique, {details['voisins']} voisins)."
        )
    return f"{label} : signal détecté."


def analyser_variable(
    valeurs: Any,
    observations: list[Any],
    methodes: Optional[list[str]] = None,
    parametres: Optional[dict[str, Any]] = None,
    libelle_variable: str = "Valeur",
    formater_valeur: Optional[Callable[[float], str]] = None,
) -> dict[str, Any]:
    """Analyse une variable et renvoie les observations atypiques détectées.

    Renvoie un dictionnaire :
    - `analysable` : la variable comporte-t-elle des valeurs numériques ?
    - `raison`     : motif de non-analyse le cas échéant ;
    - `observations`: nombre d'observations prises en compte ;
    - `rapports`   : rapport détaillé par méthode ;
    - `anomalies`  : lignes signalées (score, niveau, justification, détail
      par méthode).
    """
    forme = formater_valeur or _format_francais
    demandees = methodes or list(METHODES)
    selection = list(dict.fromkeys(m for m in demandees if m in METHODES))
    parametres_effectifs = dict(PARAMETRES_PAR_DEFAUT)
    if parametres:
        for cle, valeur in parametres.items():
            if cle in parametres_effectifs and isinstance(valeur, dict):
                parametres_effectifs[cle].update(valeur)

    arr = preparer_valeurs(valeurs)
    if arr is None or arr.size == 0:
        return {
            "analysable": False,
            "raison": "aucune valeur numérique exploitable",
            "libelle": libelle_variable,
            "observations": 0,
            "rapports": {},
            "anomalies": [],
        }

    rapports: dict[str, dict[str, Any]] = {}
    detecteurs = {
        "iqr": detecter_avec_iqr,
        "zscore": detecter_avec_zscore,
        "isolation_forest": detecter_avec_isolation_forest,
        "lof": detecter_avec_lof,
    }
    for methode in selection:
        rapports[methode] = detecteurs[methode](
            arr,
            **{k: v for k, v in parametres_effectifs[methode].items()},
        )

    signaux: dict[int, list[dict[str, Any]]] = {}
    for methode in selection:
        rapport = rapports[methode]
        if not rapport["appliquee"]:
            continue
        for resultat in rapport["resultats"]:
            if not resultat["detectee"]:
                continue
            signal = {
                "indice": resultat["indice"],
                "methode": methode,
                "label": LABELS_METHODES[methode],
                "score": resultat["score"],
                "score_brut": resultat["score_brut"],
                "justification": _justifier_methode(
                    methode,
                    LABELS_METHODES[methode],
                    resultat.get("details"),
                    float(arr[resultat["indice"]]),
                    forme,
                ),
            }
            signaux.setdefault(resultat["indice"], []).append(signal)

    anomalies: list[dict[str, Any]] = []
    for indice in sorted(signaux):
        signaux_indice = sorted(
            signaux[indice], key=lambda s: (s["score"], s["methode"]), reverse=True
        )
        nombre_methodes = len(signaux_indice)
        niveau = niveau_pour(nombre_methodes)
        valeur = float(arr[indice])
        score_max = max(s["score"] for s in signaux_indice)
        anomalies.append({
            "indice": indice,
            "valeur": valeur,
            "score": score_max,
            "niveau": niveau,
            "label_niveau": LABELS_NIVEAUX[niveau],
            "nombre_methodes": nombre_methodes,
            "methodes_detectees": [s["methode"] for s in signaux_indice],
            "justification": _construire_justification(
                libelle_variable,
                valeur,
                forme,
                signaux_indice,
                niveau,
            ),
            "par_methode": [
                {**signal, "score": round(signal["score"], 4)}
                for signal in signaux_indice
            ],
        })

    anomalies.sort(key=lambda a: (a["score"], a["niveau"]), reverse=True)
    return {
        "analysable": True,
        "raison": None,
        "libelle": libelle_variable,
        "observations": int(arr.size),
        "rapports": rapports,
        "anomalies": anomalies,
    }


def _construire_justification(
    libelle_variable: str,
    valeur: float,
    formater_valeur: Callable[[float], str],
    methodes_detectees: list[dict[str, Any]],
    niveau: str,
) -> str:
    noms = ", ".join(signal["label"] for signal in methodes_detectees)
    return (
        f"{libelle_variable} de {formater_valeur(valeur)} signalée comme "
        f"« {LABELS_NIVEAUX.get(niveau, niveau)} » par "
        f"{len(methodes_detectees)} méthode(s) indépendante(s) : {noms}. "
        "Vérification humaine requise — une valeur atypique n'est pas "
        "nécessairement une fraude."
    )