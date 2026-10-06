// Constantes partagées de l'interface « Détection d'anomalies ».
//
// Les libellés/statuts correspondent au référentiel exposé par le backend
// (`GET /api/v1/anomalies/meta`). Lexique imposé : « observation atypique »,
// « anomalie potentielle », « valeur à vérifier » — aucune observation n'est
// jamais qualifiée de fraude automatiquement.

export const METHODE_LABELS = {
  iqr: "IQR",
  zscore: "Z-score",
  isolation_forest: "Isolation Forest",
  lof: "LOF",
};

export const NIVEAU_VARIANTS = {
  observation_atypique: "info",
  anomalie_potentielle: "warning",
  valeur_a_verifier: "danger",
};

export const STATUT_VARIANTS = {
  a_verifier: "warning",
  en_cours: "info",
  confirmee: "success",
  ecartee: "neutral",
};

export const STATUTS_VERIFICATION = {
  a_verifier: "À vérifier",
  en_cours: "En cours de vérification",
  confirmee: "Atypicité confirmée",
  ecartee: "Écartée",
};