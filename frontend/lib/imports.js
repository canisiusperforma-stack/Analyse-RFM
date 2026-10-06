export function statutImportation(statut) {
  switch (statut) {
    case "termine":
      return { label: "Terminé", variant: "success" };
    case "en_cours":
      return { label: "En cours", variant: "info" };
    case "echec":
      return { label: "Échec", variant: "danger" };
    default:
      return { label: statut ?? "—", variant: "neutral" };
  }
}

export function typeErreurLabel(type) {
  const libelles = {
    type: "Type",
    doublon: "Doublon",
    obligatoire: "Valeur manquante",
  };
  return libelles[type] ?? type ?? "—";
}

export function telechargerBlob(blob, nomFichier) {
  const url = URL.createObjectURL(blob);
  const lien = document.createElement("a");
  lien.href = url;
  lien.download = nomFichier || "fichier";
  document.body.appendChild(lien);
  lien.click();
  document.body.removeChild(lien);
  URL.revokeObjectURL(url);
}

export function courtIdentifiant(identifiant) {
  if (!identifiant) return "—";
  return String(identifiant).slice(0, 10) + "…";
}