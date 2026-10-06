import api from "./api";

function entetesUtilisateur(utilisateurId) {
  if (!utilisateurId) return {};
  return { "X-Utilisateur-Id": utilisateurId };
}

export async function importerFichier({
  fichier,
  encodage = null,
  delimiteur = null,
  feuille = 0,
  colonnesObligatoires = [],
  deversement = false,
  utilisateurId = null,
}) {
  const formData = new FormData();
  formData.append("fichier", fichier);
  if (encodage) formData.append("encodage", encodage);
  if (delimiteur) formData.append("delimiteur", delimiteur);
  formData.append("feuille", String(feuille));
  formData.append("deversement", String(deversement));
  if (colonnesObligatoires.length > 0) {
    formData.append(
      "colonnes_obligatoires",
      colonnesObligatoires.join(",")
    );
  }

  const { data } = await api.post("/v1/imports", formData, {
    headers: entetesUtilisateur(utilisateurId),
  });
  return data;
}

export async function listerImportations({ limite = 50, saut = 0 } = {}) {
  const { data } = await api.get("/v1/imports", { params: { limite, saut } });
  return data;
}

export async function detailImportation(identifiant) {
  const { data } = await api.get(`/v1/imports/${identifiant}`);
  return data;
}

export async function listerRejets(identifiant, { limite = 200, saut = 0 } = {}) {
  const { data } = await api.get(`/v1/imports/${identifiant}/rejets`, {
    params: { limite, saut },
  });
  return data;
}

export async function listerBrutes(identifiant, { limite = 200, saut = 0 } = {}) {
  const { data } = await api.get(`/v1/imports/${identifiant}/brutes`, {
    params: { limite, saut },
  });
  return data;
}

export async function listerNettoyees(identifiant, { limite = 200, saut = 0 } = {}) {
  const { data } = await api.get(`/v1/imports/${identifiant}/nettoyees`, {
    params: { limite, saut },
  });
  return data;
}

export async function telechargerFichierOriginal(identifiant) {
  const { data } = await api.get(`/v1/imports/${identifiant}/fichier`, {
    responseType: "blob",
  });
  return data;
}