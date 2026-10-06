import api from "./api";

export async function recupererSynthese(exercice) {
  const { data } = await api.get("/v1/budgets", {
    params: exercice ? { exercice } : {},
  });
  return data;
}

export async function recupererExercices() {
  const { data } = await api.get("/v1/budgets/exercices");
  return data.exercices;
}