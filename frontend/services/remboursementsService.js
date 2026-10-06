import api from "./api";

export async function recupererStatistiques(exercice) {
  const { data } = await api.get("/v1/remboursements/statistiques", {
    params: exercice ? { exercice } : {},
  });
  return data;
}

export async function recupererExercices() {
  const { data } = await api.get("/v1/remboursements/exercices");
  return data.exercices;
}

export async function recupererRemboursements({
  exercice,
  recherche,
  statut,
  typePrestation,
  circuit,
  montantMin,
  montantMax,
  tri,
  ordre,
  limite,
  saut,
}) {
  const { data } = await api.get("/v1/remboursements", {
    params: {
      exercice: exercice || undefined,
      recherche: recherche || undefined,
      statut: statut || undefined,
      type_prestation: typePrestation || undefined,
      circuit: circuit || undefined,
      montant_min: montantMin || undefined,
      montant_max: montantMax || undefined,
      tri: tri || undefined,
      ordre: ordre || undefined,
      limite,
      saut,
    },
  });
  return data;
}