import api from "./api";

export async function recupererMetaPrevisions() {
  const { data } = await api.get("/v1/previsions/meta");
  return data;
}

export async function recupererDonneesPrevisions({ phase } = {}) {
  const { data } = await api.get("/v1/previsions/donnees", {
    params: { phase: phase || undefined },
  });
  return data;
}

export async function genererPrevision({
  phase,
  horizon,
  testSize,
  methode,
} = {}) {
  const { data } = await api.post("/v1/previsions/generer", {
    phase: phase || undefined,
    horizon,
    test_size: testSize,
    methode: methode || undefined,
  });
  return data;
}