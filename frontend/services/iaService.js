// Client de l'assistant conversationnel.
//
// Les points d'entrée correspondent aux questions que l'interface se pose
// réellement : quelles questions sont recevables (`/referentiel`), sur quelles
// périodes (`/exercices`), quels chemins existent (`/routes`), et que répond le
// pipeline (`/question` pour les données, `/query` pour la fusion).
//
// `/etat` n'est pas utilisé au rendu. Il teste la joignabilité du service de
// modèle et peut donc prendre plusieurs secondes : l'état affiché par
// l'interface provient de `referentiel.modele`, sans appel réseau. Le diagnostic
// reste accessible pour un dépannage.

import api from "./api";

export const MAX_HISTORIQUE = 8;

/**
 * Poser une question.
 *
 * @param {object} options
 * @param {string} options.question      Question en langage naturel.
 * @param {number|null} [options.exercice]  Exercice imposé ; `null` laisse
 *   chaque indicateur appliquer « le plus récent disponible ».
 * @param {Array<{role: string, content: string}>} [options.historique]
 *   Tours précédents. Volontairement borné : l'historique sert à la continuité
 *   de conversation, jamais de source de chiffres, et le backend n'en retient
 *   qu'un nombre limité de tours.
 * @returns {Promise<object>} Compte rendu d'exécution du pipeline.
 */
export async function poserQuestion({ question, exercice = null, historique = [] }) {
  const { data } = await api.post("/v1/assistant/question", {
    question,
    exercice: exercice ?? null,
    historique: historique.slice(-MAX_HISTORIQUE * 2),
  });
  return data;
}

/** Périmètre, garanties et catalogue des indicateurs. */
export async function recupererReferentiel() {
  const { data } = await api.get("/v1/assistant/referentiel");
  return data;
}

/**
 * Poser une question par le chemin d'orchestration.
 *
 * Contrairement à `poserQuestion`, qui suppose le chemin données et répond sur
 * le « plus récent disponible », cette fonction laisse le backend **choisir le
 * chemin** (`DATA`, `RAG`, `DATA_RAG` ou hors périmètre) et **demander une
 * précision** si la période manque. Le sélecteur d'exercice de la page est donc
 * transmis ici avec un sens différent : il lève l'ambiguïté au lieu d'imposer
 * un choix par défaut — ce qui est le comportement attendu, puisqu'une
 * comparaison entre un chiffre observé et une règle n'a pas de sens sur un
 * exercice que l'utilisateur n'a pas demandé.
 *
 * @param {object} options
 * @param {string} options.question
 * @param {number|null} [options.exercice]  Exercice imposé, ou `null` pour
 *   laisser le backend demander la précision.
 * @param {string[]} [options.documents]  Identifiants de documents à
 *   consulter. Restreint la recherche sans jamais élargir ce que l'utilisateur
 *   a le droit de lire.
 * @param {Array<{role: string, content: string}>} [options.historique]
 * @returns {Promise<object>} Réponse d'orchestration.
 */
export async function poserRequete({
  question,
  exercice = null,
  documents = [],
  historique = [],
}) {
  const { data } = await api.post("/v1/assistant/query", {
    question,
    exercice: exercice ?? null,
    documents,
    historique: historique.slice(-MAX_HISTORIQUE * 2),
  });
  return data;
}

/** Chemins de routage, seuils appliqués et état de la fusion. */
export async function recupererRoutes() {
  const { data } = await api.get("/v1/assistant/routes");
  return data;
}

/** Exercices disponibles dans au moins une source. */
export async function recupererExercices() {
  const { data } = await api.get("/v1/assistant/exercices");
  return Array.isArray(data?.exercices) ? data.exercices : [];
}

/** Diagnostic du service de modèle de langage (dépannage). */
export async function verifierEtatModele() {
  const { data } = await api.get("/v1/assistant/etat");
  return data;
}
