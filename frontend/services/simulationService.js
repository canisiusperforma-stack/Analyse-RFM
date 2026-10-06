import api from "./api";

export async function recupererScenariosSimulation() {
  const { data } = await api.get("/v1/simulations/scenarios");
  return data;
}

export async function calculerSimulation({
  budgetHypothetique,
  nombreDossiers,
  montantMoyen,
  ecartDossiersPct,
  ecartMontantPct,
} = {}) {
  const { data } = await api.post("/v1/simulations/calculer", {
    budget_hypothetique: budgetHypothetique,
    nombre_dossiers: nombreDossiers,
    montant_moyen: montantMoyen,
    ecart_dossiers_pct: ecartDossiersPct,
    ecart_montant_pct: ecartMontantPct,
  });
  return data;
}