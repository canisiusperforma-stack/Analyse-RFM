// Client de l'administration des comptes.
//
// Chaque fonction correspond à une route de `app/api/routes/utilisateurs.py`.
// Le frontend n'invente aucune règle : il transmet, et restitue. En particulier,
// il ne décide jamais qu'un rôle est « attribuable » ni qu'un compte peut être
// désactivé — le backend refuse par exemple de modifier son propre rôle, et un
// écran qui l'autoriserait afficherait un échec garanti.
//
// La création ne renvoie pas de jeton : un compte créé par un administrateur
// n'est pas connecté, il doit se connecter avec le mot de passe provisoire.

import api from "./api";

/**
 * Liste paginée des comptes (profil public uniquement).
 *
 * @param {object} [options]
 * @param {number} [options.limite] 1 à 500, 50 par défaut.
 * @param {number} [options.saut]   Décalage, 0 par défaut.
 * @param {string|null} [options.role]  Filtre RBAC (`ADMIN`, `RESPONSABLE`…).
 * @param {boolean|null} [options.actif] Filtre d'état du compte.
 * @returns {Promise<{total: number, limite: number, saut: number, utilisateurs: object[]}>}
 */
export async function listerUtilisateurs({
  limite = 50,
  saut = 0,
  role = null,
  actif = null,
} = {}) {
  const params = { limite, saut };
  if (role) params.role = role;
  if (actif !== null && actif !== undefined) params.actif = actif;
  const { data } = await api.get("/v1/utilisateurs", { params });
  return data;
}

/**
 * Crée un compte avec un rôle RBAC (permission `utilisateurs:creer`).
 *
 * Le mot de passe est transmis en clair sur le canal chiffré puis haché côté
 * backend ; aucun jeton n'est émis, l'intéressé doit se connecter.
 *
 * @param {object} compte
 * @param {string} compte.prenom
 * @param {string} compte.nom
 * @param {string} compte.email
 * @param {string} compte.motDePasse 8 caractères minimum.
 * @param {string} compte.role
 * @returns {Promise<object>} Profil public du compte créé.
 */
export async function creerUtilisateur({ prenom, nom, email, motDePasse, role }) {
  const { data } = await api.post("/v1/utilisateurs", {
    prenom,
    nom,
    email,
    mot_de_passe: motDePasse,
    role,
  });
  return data;
}

/**
 * Modifie l'identité ou l'état d'un compte (`utilisateurs:modifier`).
 *
 * L'e-mail et le mot de passe sont volontairement absents du corps : le backend
 * ne les modifie pas. Un mot de passe perdu se réinitialise côté serveur, pas
 * depuis cet écran.
 *
 * @param {string} identifiant
 * @param {{prenom?: string, nom?: string, actif?: boolean}} [changements]
 * @returns {Promise<object>} Profil public du compte modifié.
 */
export async function modifierUtilisateur(
  identifiant,
  { prenom, nom, actif } = {}
) {
  const payload = {};
  if (prenom !== undefined) payload.prenom = prenom;
  if (nom !== undefined) payload.nom = nom;
  if (actif !== undefined) payload.actif = actif;
  const { data } = await api.patch(`/v1/utilisateurs/${identifiant}`, payload);
  return data;
}

/**
 * Réattribue un rôle RBAC (`utilisateurs:changer_role`).
 *
 * Le backend interdit cette opération sur le propre compte de l'acteur : la
 * modifier reviendrait à se retirer soi-même l'accès à l'administration.
 */
export async function changerRoleUtilisateur(identifiant, role) {
  const { data } = await api.patch(`/v1/utilisateurs/${identifiant}/role`, {
    role,
  });
  return data;
}

/** Supprime définitivement un compte, sauf le sien propre. */
export async function supprimerUtilisateur(identifiant) {
  await api.delete(`/v1/utilisateurs/${identifiant}`);
}
