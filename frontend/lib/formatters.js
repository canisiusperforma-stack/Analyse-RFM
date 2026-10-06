const numberFormatter = new Intl.NumberFormat("fr-FR");
const currencyFormatter = new Intl.NumberFormat("fr-FR", {
  minimumFractionDigits: 0,
  maximumFractionDigits: 0,
});
const percentFormatter = new Intl.NumberFormat("fr-FR", {
  style: "percent",
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
});
const scoreFormatter = new Intl.NumberFormat("fr-FR", {
  minimumFractionDigits: 0,
  maximumFractionDigits: 2,
});
const dateFormatter = new Intl.DateTimeFormat("fr-FR", {
  day: "2-digit",
  month: "2-digit",
  year: "numeric",
});
const dateTimeFormatter = new Intl.DateTimeFormat("fr-FR", {
  day: "2-digit",
  month: "2-digit",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
});
const shortDateFormatter = new Intl.DateTimeFormat("fr-FR", {
  day: "2-digit",
  month: "short",
  year: "numeric",
});

export function formatNumber(value) {
  if (value == null || Number.isNaN(Number(value))) return "—";
  return numberFormatter.format(Number(value));
}

export function formatCurrency(value) {
  if (value == null || Number.isNaN(Number(value))) return "—";
  return `${currencyFormatter.format(Number(value))} Ar`;
}

export function formatSignedCurrency(value) {
  if (value == null || Number.isNaN(Number(value))) return "—";
  const montant = Number(value);
  const signe = montant > 0 ? "+" : montant < 0 ? "−" : "";
  return `${signe}${currencyFormatter.format(Math.abs(montant))} Ar`;
}

export function compactCurrency(value) {
  const montant = Number(value);
  if (Number.isNaN(montant)) return "";
  if (Math.abs(montant) >= 1e9) return `${(montant / 1e9).toFixed(1)} Md`;
  if (Math.abs(montant) >= 1e6) return `${(montant / 1e6).toFixed(0)} M`;
  return `${Math.round(montant)} Ar`;
}

export function formatPercent(value) {
  if (value == null || Number.isNaN(Number(value))) return "—";
  return percentFormatter.format(Number(value));
}

export function formatScore(value) {
  if (value == null || Number.isNaN(Number(value))) return "—";
  return scoreFormatter.format(Number(value));
}

export function formatBytes(value) {
  if (value == null || Number.isNaN(Number(value))) return "—";
  const octets = Number(value);
  if (octets < 1024) return `${octets} o`;
  if (octets < 1024 * 1024) return `${(octets / 1024).toFixed(1)} Ko`;
  return `${(octets / (1024 * 1024)).toFixed(2)} Mo`;
}

export function formatDate(value) {
  if (!value) return "—";
  try {
    return dateFormatter.format(new Date(value));
  } catch {
    return "—";
  }
}

export function formatDateTime(value) {
  if (!value) return "—";
  try {
    return dateTimeFormatter.format(new Date(value));
  } catch {
    return "—";
  }
}

export function formatShortDate(value) {
  if (!value) return "—";
  try {
    return shortDateFormatter.format(new Date(value));
  } catch {
    return "—";
  }
}

export function initials(name) {
  if (!name) return "?";
  return name
    .trim()
    .split(/\s+/)
    .slice(0, 2)
    .map((w) => w.charAt(0).toUpperCase())
    .join("");
}