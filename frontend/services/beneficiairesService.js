import api from "./api";

export async function recupererStatistiques(exercice) {
  const { data } = await api.get("/v1/beneficiaires/statistiques", {
    params: exercice ? { exercice } : {},
  });
  return data;
}

export async function recupererExercices() {
  const { data } = await api.get("/v1/beneficiaires/exercices");
  return data.exercices;
}

export async function recupererBeneficiaires({
  exercice,
  recherche,
  situation,
  categorie,
  genre,
  direction,
  statutDossier,
  rfm,
  tri,
  ordre,
  limite,
  saut,
}) {
  const { data } = await api.get("/v1/beneficiaires", {
    params: {
      exercice: exercice || undefined,
      recherche: recherche || undefined,
      situation: situation || undefined,
      categorie: categorie || undefined,
      genre: genre || undefined,
      direction: direction || undefined,
      statut_dossier: statutDossier || undefined,
      rfm: rfm || undefined,
      tri: tri || undefined,
      ordre: ordre || undefined,
      limite,
      saut,
    },
  });
  return data;
}