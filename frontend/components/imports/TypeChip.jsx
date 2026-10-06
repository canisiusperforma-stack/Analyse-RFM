import { cn } from "@/lib/utils";

const LIBELLES = {
  date: "Date",
  montant: "Montant",
  entier: "Entier",
  decimal: "Décimal",
  texte: "Texte",
  vide: "Vide",
};

function classeType(type) {
  if (type === "decimal") return "type-chip--decimal";
  if (type in LIBELLES) return `type-chip--${type}`;
  return "";
}

export default function TypeChip({ type, className }) {
  const libelle = LIBELLES[type] ?? type ?? "—";
  return (
    <span className={cn("type-chip", classeType(type), className)}>
      {libelle}
    </span>
  );
}