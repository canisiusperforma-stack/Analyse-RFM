// État de la plateforme.
//
// `/api/sante` est la seule route publique de l'API : elle ne demande aucune
// permission et ne renvoie aucune donnée métier. C'est ce qui permet à l'écran
// d'administration de distinguer « l'API ne répond pas » de « la base est
// injoignable » — deux pannes très différentes, que la seule page blanche ne
// distingue pas.

import api from "./api";

/**
 * Vérifie l'API et la connexion à MongoDB.
 *
 * @returns {Promise<{statut: "ok"|"degrade", api: string, mongodb: string,
 *   version?: string, environnement?: string, detail?: string|null,
 *   horodatage?: string}>}
 */
export async function verifierSante() {
  const { data } = await api.get("/sante");
  return data;
}
