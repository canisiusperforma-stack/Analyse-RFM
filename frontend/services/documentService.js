// Client de la base documentaire.
//
// Chaque fonction correspond à une route de `app/api/routes/documents.py`. Le
// frontend n'y ajoute aucune logique : il transmet, et restitue. En
// particulier, il ne réévalue jamais une classification ni ne décide qu'un
// document est indexable — ces décisions appartiennent au backend, qui est la
// seule autorité sur ce qu'un utilisateur est autorisé à voir.
//
// Deux points méritent un commentaire.
//
// Dépôt
//   Le `Content-Type` est forcé à `multipart/form-data`. L'instance axios
//   déclare `application/json` par défaut, or axios convertit un `FormData`
//   en JSON dès qu'il voit cet en-tête : le fichier Parts — et donc le contenu
//   du document — serait perdu avant l'envoi. Axios retire ensuite lui-même
//   l'en-tête, sans la *boundary*, pour que le navigateur l'écrive.
//
// Confidentialité
//   Le dépôt crée un document `interne`. Classer un document `restreinte` ou
//   `confidentielle` exige la permission `documents:acces`, réservée à
//   l'administrateur : l'interface ne propose donc ce choix qu'à qui peut
//   l'appliquer, et `modifierAccesDocument` est la seule voie pour le changer
//   ensuite.

import api from "./api";

/** En-tête imposé pour qu'axios n'ouvre pas le `FormData` en JSON. */
const MULTIPART = { "Content-Type": "multipart/form-data" };

/**
 * Dépose un document dans la base documentaire.
 *
 * @param {object} options
 * @param {File} options.fichier              Fichier déposé.
 * @param {string} [options.description]      Description libre.
 * @param {string} [options.confidentialite]  `interne` (défaut), `restreinte`
 *   ou `confidentielle`. Les deux derniers niveaux exigent la permission
 *   `documents:acces`.
 * @param {string[]} [options.rolesAutorises]      Rôles autorisés à lire.
 * @param {string[]} [options.utilisateursAutorises] Identifiants nommés.
 * @returns {Promise<{document: object, indexation: object|null, indexation_demandee: boolean}>}
 */
export async function televerserDocument({
  fichier,
  description = null,
  confidentialite = "interne",
  rolesAutorises = [],
  utilisateursAutorises = [],
} = {}) {
  const formData = new FormData();
  formData.append("fichier", fichier);
  if (description) formData.append("description", description);
  formData.append("confidentialite", confidentialite);
  rolesAutorises.forEach((role) => formData.append("roles_autorises", role));
  utilisateursAutorises.forEach((identifiant) =>
    formData.append("utilisateurs_autorises", identifiant)
  );

  const { data } = await api.post("/v1/documents", formData, {
    headers: MULTIPART,
  });
  return data;
}

/**
 * Liste les documents accessibles par l'appelant.
 *
 * Le filtrage est fait par la base : un document interdit n'est pas renvoyé,
 * et son existence n'est pas révélée.
 *
 * @param {{limite?: number, saut?: number}} [options]
 * @returns {Promise<{documents: object[], total: number, limite: number, saut: number}>}
 */
export async function listerDocuments({ limite = 50, saut = 0 } = {}) {
  const { data } = await api.get("/v1/documents", { params: { limite, saut } });
  return data;
}

/**
 * Métadonnées d'un document, avec le motif d'un échec d'indexation.
 *
 * @param {string} identifiant
 * @returns {Promise<{document: object, erreur_indexation: string|null}>}
 */
export async function consulterDocument(identifiant) {
  const { data } = await api.get(`/v1/documents/${identifiant}`);
  return data;
}

/** Fichier d'origine, tel qu'il a été déposé. */
export async function telechargerDocument(identifiant) {
  const { data } = await api.get(`/v1/documents/${identifiant}/telecharger`, {
    responseType: "blob",
  });
  return data;
}

/** Supprime le document, ses extraits et son fichier d'origine. */
export async function supprimerDocument(identifiant) {
  const { data } = await api.delete(`/v1/documents/${identifiant}`);
  return data;
}

/**
 * Relance le pipeline d'indexation sur un document.
 *
 * Idempotent : les extraits précédents sont remplacés, jamais doublés.
 *
 * @param {string} identifiant
 * @param {{force?: boolean}} [options] `force=false` n'indexe que si le
 *   document ne l'est pas déjà.
 */
export async function indexerDocument(identifiant, { force = true } = {}) {
  const { data } = await api.post(`/v1/documents/${identifiant}/indexer`, null, {
    params: { force },
  });
  return data;
}

/**
 * Fixe la confidentialité d'un document (permission `documents:acces`).
 *
 * Le changement est répercuté sur les extraits déjà indexés. Un document classé
 * sans rôle autorisé est refusé côté backend : il serait inaccessible à tous.
 *
 * @param {string} identifiant
 * @param {object} options
 * @param {string} options.confidentialite
 * @param {string[]} [options.rolesAutorises]
 * @param {string[]} [options.utilisateursAutorises]
 */
export async function modifierAccesDocument(
  identifiant,
  { confidentialite, rolesAutorises = [], utilisateursAutorises = [] } = {}
) {
  const { data } = await api.patch(`/v1/documents/${identifiant}/acces`, {
    confidentialite,
    roles_autorises: rolesAutorises,
    utilisateurs_autorises: utilisateursAutorises,
  });
  return data;
}

/** État de la base, restreint aux documents accessibles à l'appelant. */
export async function statistiquesDocuments() {
  const { data } = await api.get("/v1/documents/statistiques");
  return data;
}

/**
 * Périmètre et garanties de l'assistant documentaire.
 *
 * Sert à afficher ce que le pipeline fait *réellement* : une interface qui
 * annoncerait des capacités absentes de la configuration donnerait un avis
 * trompeur sur la portée de la recherche.
 */
export async function referentielDocuments() {
  const { data } = await api.get("/v1/documents/referentiel");
  return data;
}

/**
 * Recherche des extraits, sans appel à un modèle.
 *
 * Renvoie une liste vide lorsque rien n'atteint le seuil de pertinence : mieux
 * vaut signaler une absence que présenter un extrait sans rapport.
 *
 * @param {object} options
 * @param {string} options.q                Question ou termes recherchés.
 * @param {number} [options.nombre]         Extraits renvoyés (0 = défaut).
 * @param {string[]} [options.documents]    Restreint à ces documents.
 */
export async function rechercherExtraits({ q, nombre = 0, documents = [] } = {}) {
  const params = { q };
  if (nombre > 0) params.nombre = nombre;
  if (documents.length > 0) params.documents = documents;

  const { data } = await api.get("/v1/documents/recherche", { params });
  return data;
}

/**
 * Pose une question au pipeline documentaire.
 *
 * Le chemin est imposé par le backend : sans extrait autorisé au-dessus du
 * seuil, `mode` vaut `absence` et le modèle n'est pas appelé.
 *
 * @param {object} options
 * @param {string} options.question
 * @param {number} [options.nombre]
 * @param {string[]} [options.documents]
 */
export async function poserQuestionDocumentaire({
  question,
  nombre = null,
  documents = [],
} = {}) {
  const corps = { question };
  if (nombre) corps.nombre = nombre;
  if (documents.length > 0) corps.documents = documents;

  const { data } = await api.post("/v1/documents/question", corps);
  return data;
}
