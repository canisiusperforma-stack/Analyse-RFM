import api from "./api";

export async function connexion({ email, motDePasse }) {
  const { data } = await api.post("/v1/auth/connexion", {
    email,
    mot_de_passe: motDePasse,
  });
  return data;
}

export async function inscription({
  prenom,
  nom,
  email,
  motDePasse,
  role = null,
}) {
  const { data } = await api.post("/v1/auth/inscription", {
    prenom,
    nom,
    email,
    mot_de_passe: motDePasse,
    ...(role ? { role } : {}),
  });
  return data;
}

export async function recupererMoi() {
  const { data } = await api.get("/v1/auth/me");
  return data;
}