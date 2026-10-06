import api from "./api";

export async function recupererExercices() {
  const { data } = await api.get("/v1/dashboard/exercices");
  return data.exercices ?? [];
}

export async function recupererSynthese(exercice) {
  const { data } = await api.get("/v1/dashboard/synthese", {
    params: exercice ? { exercice } : {},
  });
  return data;
}