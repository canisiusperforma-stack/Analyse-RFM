import api from "./api";

export async function recupererAnalyseTemporelle(exercice) {
  const { data } = await api.get("/v1/analyses/temporelle", {
    params: exercice ? { exercice } : {},
  });
  return data;
}

export async function recupererExercicesAnalyses() {
  const { data } = await api.get("/v1/analyses/exercices");
  return data.exercices;
}

export async function recupererStatistiquesAnalyse(exercice) {
  const { data } = await api.get("/v1/analyses/statistiques", {
    params: exercice ? { exercice } : {},
  });
  return data;
}