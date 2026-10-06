import api from "./api";

export async function recupererExercicesAnomalies() {
  const { data } = await api.get("/v1/anomalies/exercices");
  return data.exercices;
}

export async function recupererReferentielAnomalies() {
  const { data } = await api.get("/v1/anomalies/meta");
  return data;
}

export async function lancerDetectionAnomalies({
  exercice,
  variables,
  methodes,
  parametres,
  stocker = true,
} = {}) {
  const { data } = await api.post("/v1/anomalies/detection", {
    exercice: exercice ?? undefined,
    variables: variables || undefined,
    methodes: methodes || undefined,
    parametres: parametres || undefined,
    stocker,
  });
  return data;
}

export async function recupererAnomalies({
  exercice,
  statutVerification,
  niveau,
  methode,
  variable,
  recherche,
  tri,
  ordre,
  limite,
  saut,
}) {
  const { data } = await api.get("/v1/anomalies", {
    params: {
      exercice: exercice || undefined,
      statut_verification: statutVerification || undefined,
      niveau: niveau || undefined,
      methode: methode || undefined,
      variable: variable || undefined,
      recherche: recherche || undefined,
      tri: tri || undefined,
      ordre: ordre || undefined,
      limite,
      saut,
    },
  });
  return data;
}

export async function recupererAnomalie(id) {
  const { data } = await api.get(`/v1/anomalies/${id}`);
  return data;
}

export async function mettreAJourVerificationAnomalie(
  id,
  { statutVerification, commentaire } = {}
) {
  const { data } = await api.patch(`/v1/anomalies/${id}/verification`, {
    statut_verification: statutVerification,
    commentaire: commentaire?.trim() || undefined,
  });
  return data;
}