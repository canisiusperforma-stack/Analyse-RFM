import api from "./api";
import { telechargerBlob } from "@/lib/imports";

function nomFichierDepuisDisposition(disposition) {
  if (!disposition) return null;
  const avecEtoile = disposition.match(/filename\*=UTF-8''([^;]+)/i);
  if (avecEtoile) return decodeURIComponent(avecEtoile[1]);
  const simple = disposition.match(/filename="?([^";]+)"?/i);
  return simple ? simple[1] : null;
}

export async function recupererExercices() {
  const { data } = await api.get("/v1/rapports/exercices");
  return data.exercices ?? [];
}

export async function recupererRapport(exercice) {
  const { data } = await api.get(`/v1/rapports/${exercice}`);
  return data;
}

export async function exporterExcel(exercice) {
  const reponse = await api.get(`/v1/rapports/${exercice}/excel`, {
    responseType: "blob",
  });
  const nom = nomFichierDepuisDisposition(
    reponse.headers?.["content-disposition"]
  );
  telechargerBlob(
    reponse.data,
    nom || `Rapport_RFM_${exercice}_Export_Structuré.xlsx`
  );
}