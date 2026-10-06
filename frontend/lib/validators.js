export const EMAIL_REGEX = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export function required(value, fieldName) {
  if (value === null || value === undefined) return `${fieldName} est requis.`;
  if (typeof value === "string" && value.trim() === "")
    return `${fieldName} est requis.`;
  return null;
}

export function email(value) {
  if (!value) return null;
  if (!EMAIL_REGEX.test(value)) return "Adresse e-mail invalide.";
  return null;
}

export function minLength(value, min, fieldName) {
  if (!value) return null;
  if (String(value).length < min)
    return `${fieldName} doit contenir au moins ${min} caractères.`;
  return null;
}

export function maxLength(value, max, fieldName) {
  if (!value) return null;
  if (String(value).length > max)
    return `${fieldName} ne doit pas dépasser ${max} caractères.`;
  return null;
}

export function numberValue(value, fieldName) {
  if (value === null || value === undefined || value === "") return null;
  if (isNaN(Number(value))) return `${fieldName} doit être un nombre.`;
  return null;
}

export function positive(value, fieldName) {
  if (value === null || value === undefined || value === "") return null;
  const n = Number(value);
  if (isNaN(n) || n < 0) return `${fieldName} doit être un nombre positif.`;
  return null;
}

export function combineErrors(...errors) {
  return errors.filter(Boolean)[0] || null;
}