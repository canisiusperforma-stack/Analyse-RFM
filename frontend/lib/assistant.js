// Interprétation d'un compte rendu d'assistant, sans dépendance réseau.
//
// Ce module contient la logique d'affichage pure : statut d'un calcul, lecture
// de la provenance, choix des libellés. Il est volontairement séparé de
// `services/iaService.js` afin de rester testable sans axios et sans serveur.
//
// Règle appliquée partout ici : le client n'invente et ne recalcule aucune
// valeur. Il affiche le champ `valeur_affichee` que le backend produit avec
// `indicator_service.formater_valeur` — la même chaîne que celle que le
// contrôle numérique a confrontée à l'index des données autorisées, et celle
// que la réponse rédigée reprend. Formater à nouveau en JavaScript créerait un
// second rendu, susceptible d'afficher un chiffre différent de celui que le
// serveur a validé.

/** Bornes du contrat d'entrée, alignées sur la configuration du backend. */
export const MAX_QUESTION = 2000;

/** Statut du calcul -> variante de badge de la charte. */
export const VARIANTES_STATUT = {
  disponible: "success",
  partiel: "warning",
  absent: "warning",
  erreur: "danger",
};

/** Libellé lisible d'un statut de calcul. */
export function libelleStatut(statut) {
  switch (statut) {
    case "disponible":
      return "Donnée disponible";
    case "partiel":
      return "Donnée partielle";
    case "absent":
      return "Donnée absente";
    default:
      return "Non calculé";
  }
}

/** Variante de badge d'un statut de calcul. */
export function varianteStatut(statut) {
  return VARIANTES_STATUT[statut] || "neutral";
}

/** Libellé lisible de l'intention reconnue par l'analyse. */
export function libelleIntention(intention) {
  switch (intention) {
    case "budget":
      return "Budget";
    case "population":
      return "Population";
    case "remboursements":
      return "Remboursements";
    case "analyse_temporelle":
      return "Analyse temporelle";
    case "statistiques":
      return "Statistiques";
    case "anomalies":
      return "Anomalies";
    case "previsions":
      return "Prévisions";
    case "hors_perimetre":
      return "Hors périmètre";
    default:
      return "Non identifiée";
  }
}

/**
 * Variante de badge de la provenance rédactionnelle.
 *
 * `reponse_rejetee` signale que le modèle a bien produit un texte mais que sa
 * réponse a été écartée : les chiffres affichés sont alors ceux du backend,
 * présentés par le code. Cette distinction est la garantie centrale de
 * l'assistant ; elle mérite d'être visible, pas seulement stockée.
 */
export function varianteProvenance(reponse) {
  if (reponse?.reponse_rejetee) return "warning";
  return reponse?.generee_par === "llm" ? "primary" : "neutral";
}

/** Texte de la pastille de provenance. */
export function libelleProvenance(reponse) {
  if (reponse?.reponse_rejetee) return "Réponse backend (modèle écarté)";
  if (reponse?.generee_par === "llm") return "Réponse rédigée par le modèle";
  return "Réponse produite par le backend";
}

/**
 * Une réponse dont les chiffres ont été écartés mérite-t-elle un avertissement
 * dédié ? Le cas est distinct d'une simple réponse backend : il signale que le
 * modèle a été sollicité puis délaissé, ce que l'utilisateur doit savoir.
 */
export function avertissementModeleEcarte(reponse) {
  const rejet = reponse?.reponse_rejetee;
  if (!rejet) return null;
  if (typeof rejet === "string") return rejet;
  const ecarts = Array.isArray(rejet.ecarts) ? rejet.ecarts : [];
  if (!ecarts.length) return "La réponse du modèle a été écartée.";
  return `${ecarts.length} valeur(s) non autorisées ont été retirées de la réponse du modèle.`;
}

/** Mesures du résultat structuré, jamais `null`. */
export function mesures(reponse) {
  const liste = reponse?.resultat?.mesures;
  return Array.isArray(liste) ? liste : [];
}

/**
 * Mesures à partager en pastilles sous la réponse.
 *
 * La mesure principale est déjà contenue dans le texte rédigé par le backend
 * (il l'ouvre par « libellé - valeur ») : la répéter dans l'interface ferait
 * afficher deux fois le même nombre. Ne sont donc retenues que les mesures
 * complémentaires, plus le texte de synthèse d'un calcul sans valeur chiffrée.
 */
export function mesuresSecondaires(reponse) {
  const toutes = mesures(reponse);
  if (toutes.length <= 1) return [];
  return toutes.slice(1);
}

/** En-tête d'une réponse : indicateur reconnu, statut et exercice retenu. */
export function resumeReponse(reponse) {
  if (!reponse) return null;
  const resultat = reponse.resultat || {};
  return {
    indicateur: resultat.indicateur || null,
    libelle: resultat.libelle || null,
    statut: resultat.statut || null,
    unite: resultat.unite || null,
    note: resultat.note || null,
    absence: resultat.absence || null,
    exercice: exerciceUtilise(reponse),
  };
}

/**
 * Exercice réellement utilisé.
 *
 * Il est porté par l'enveloppe, et non par le résultat : c'est la valeur que le
 * service a effectivement appliquée, ce qui peut différer de l'exercice demandé
 * si la question n'en nommait aucun.
 */
export function exerciceUtilise(reponse) {
  return reponse?.exercice ?? null;
}

/** Le tableau structuré est-il affichable ? */
export function tableauAffichable(reponse) {
  const tableau = reponse?.resultat?.tableau;
  if (!tableau) return null;
  if (!Array.isArray(tableau.colonnes) || !Array.isArray(tableau.lignes)) return null;
  if (!tableau.colonnes.length || !tableau.lignes.length) return null;
  return tableau;
}

/** Découpe une réponse en paragraphes affichables. */
export function paragraphes(texte) {
  if (!texte) return [];
  return String(texte)
    .split(/\n+/)
    .map((bloc) => bloc.trim())
    .filter(Boolean);
}

/** Avertissements du backend, vidés de leurs entrées vides. */
export function avertissementsVisibles(reponse) {
  const avertissements = reponse?.avertissements;
  return Array.isArray(avertissements) ? avertissements.filter(Boolean) : [];
}

// ---------------------------------------------------------------------------
// Chemin d'orchestration (fusion données + documents)
// ---------------------------------------------------------------------------
//
// Tout ce qui suit lit la réponse de `POST /assistant/query`, qui porte deux
// provenances distinctes. La distinction n'est pas cosmétique : `sources`
// décrit ce que le backend a interrogé pour calculer, `documents` décrit les
// extraits qui portent les règles. Un affichage qui les confondrait suggérerait
// qu'un chiffre provient d'un document, ce qui est faux par construction.
//
// Chaque fonction est défensive sur `null` et sur un objet vide : la réponse
// peut appartenir à l'ancien chemin `/question`, qui ne connaît aucun de ces
// champs. Les tests verrouillent ce comportement.

/** Chemins possibles, avec leur libellé. */
export const LIBELLES_INTENT = {
  DATA: "Données calculées",
  RAG: "Documents",
  DATA_RAG: "Données et documents",
  INCONNUE: "Hors périmètre",
};

/**
 * Libellé du chemin emprunté.
 *
 * Un chemin inconnu ne doit pas afficher `undefined` : le repli sur `null`
 * laisse l'interface n'afficher aucune pastille plutôt que d'inventer un nom
 * de chemin. L'API est typée, mais une réponse stockée en localStorage issue
 * d'une version antérieure ne l'est pas forcément.
 */
export function libelleIntent(intent) {
  return LIBELLES_INTENT[intent] ?? null;
}

/** Le chemin a-t-il séparé les données des documents ? */
export function estFusion(reponse) {
  return reponse?.intent === "DATA_RAG";
}

/** Bloc de données structuré, ou `null`. */
export function blocDonnees(reponse) {
  return reponse?.data ?? null;
}

/**
 * Mesures du bloc de données.
 *
 * Lues dans `data.mesures` et non dans `resultat.mesures` : `resultat` est le
 * compte rendu brut conservé pour l'audit, tandis que `data` est exactement ce
 * que le modèle a reçu. Un chiffre affiché doit venir du second — sinon
 * l'interface montrerait une valeur intermédiaire que le contrôle n'a jamais
 * vu.
 */
export function mesuresDonnees(reponse) {
  const liste = reponse?.data?.mesures;
  return Array.isArray(liste) ? liste : [];
}

/** Tableau du bloc de données, s'il est affichable. */
export function tableauDonnees(reponse) {
  const tableau = reponse?.data?.tableau;
  if (!tableau) return null;
  if (!Array.isArray(tableau.colonnes) || !Array.isArray(tableau.lignes)) return null;
  if (!tableau.colonnes.length || !tableau.lignes.length) return null;
  return tableau;
}

/** Extraits documentaires retenus, jamais `null`. */
export function documents(reponse) {
  const liste = reponse?.documents;
  return Array.isArray(liste) ? liste : [];
}

/**
 * Les documents doivent-ils être affichés ?
 *
 * Le seuil est l'existence d'au moins un extrait, et non le chemin `RAG` ou
 * `DATA_RAG` : une recherche menée sans succès laisse `documents` vide, et
 * afficher un bloc « Documents » alors qu'il n'y en a aucun laisserait croire
 * qu'une recherche a eu lieu.
 */
export function documentsAffichables(reponse) {
  return documents(reponse).length > 0;
}

/** Limites annoncées par le backend, vidées de leurs entrées vides. */
export function limitesVisibles(reponse) {
  const limites = reponse?.limites;
  return Array.isArray(limites) ? limites.filter(Boolean) : [];
}

/**
 * Question de précision à poser à l'utilisateur, ou `null`.
 *
 * Le backend renvoie un objet `{motif, question, parametres_manquants}` — le
 * paramètre manquant est utile à un appelant d'API, qui peut alors reformuler
 * sa requête sans deviner. L'interface n'en affiche que la question : c'est la
 * seule des trois qui s'adresse à l'utilisateur. `motif` fait doublon avec
 * `analyse.raison`, déjà exposé par `raisonChemin`.
 *
 * Renvoyer l'objet entier Crashait le rendu : le composant l'écrit comme un
 * enfant React, et React refuse un objet. La chaîne est aussi acceptée, pour
 * que le rendu ne casse pas sur une réponse produite par une version antérieure.
 */
export function clarification(reponse) {
  const demande = reponse?.clarification;
  if (typeof demande === "string") return demande.trim() || null;
  const question = demande?.question;
  return typeof question === "string" && question.trim() ? question : null;
}

/** Confiance du routage, en pourcentage arrondi, ou `null`. */
export function confiancePourcent(reponse) {
  const valeur = reponse?.confidence;
  if (typeof valeur !== "number" || Number.isNaN(valeur)) return null;
  return Math.round(valeur * 100);
}

/**
 * Justification du choix de chemin, une ligne.
 *
 * Sert au détail dépliable : l'utilisateur peut contester un chemin, et une
 * raison affichée est la seule chose qui lui permette de voir si l'erreur vient
 * de sa formulation ou du routeur.
 */
export function raisonChemin(reponse) {
  const raison = reponse?.analyse?.raison;
  return typeof raison === "string" && raison.trim() ? raison : null;
}

/**
 * Questions d'amorce.
 *
 * Elles couvrent volontairement les trois chemins de routage, et pas seulement
 * le calcul : un taux d'exécution (données), le seuil qu'un texte fixe (textes),
 * et une question où les deux se rencontrent — comparer un chiffre observé à
 * une règle. C'est cette dernière qui montre pourquoi la fusion est utile, et
 * c'est aussi celle qui décide si l'utilisateur doit lire des chiffres *et* une
 * citation.
 */
export const QUESTIONS_EXEMPLES = [
  "Quel est le taux d'exécution du budget RFM en 2025 ?",
  "Quels taux d'exécution sontopaedic imposés par les textes en vigueur ?",
  "Le taux d'exécution du budget RFM respecte-t-il le seuil fixé par le texte ?",
  "Combien de pensionnés ont bénéficié du RFM en 2025 ?",
];

/** Questions hors périmètre, pour montrer que la limite est assumée. */
export const QUESTIONS_HORS_PERIMETRE = [
  "Quel temps fera-t-il à Antananarivo demain ?",
];
