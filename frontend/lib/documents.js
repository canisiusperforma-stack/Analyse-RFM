// Libellés et aides de la base documentaire.
//
// Les valeurs proviennent du backend (`app/models/document.py`,
// `app/rag/retriever.py`). Ce module ne fait que les traduire pour l'affichage :
// il n'invente aucun statut et n'en complète aucun. Un niveau ou un état
// inconnu est rendu tel quel, avec la variante neutre — afficher « interne » à
// la place d'une valeur illurée ferait porter à un document confidential une
// étiquette qui n'est pas la sienne.

import {
  FileJson,
  FileSpreadsheet,
  FileText,
  FileType,
  ShieldAlert,
  ShieldCheck,
  Users,
} from "lucide-react";

/** Niveau de diffusion d'un document, du plus ouvert au plus fermé. */
export const NIVEAUX_CONFIDENTIALITE = [
  {
    valeur: "interne",
    label: "Interne",
    variante: "neutral",
    icone: ShieldCheck,
    description:
      "Tous les utilisateurs disposant de la permission de consultation.",
  },
  {
    valeur: "restreinte",
    label: "Restreinte",
    variante: "warning",
    icone: Users,
    description: "Uniquement les rôles désignés dans la liste autorisée.",
  },
  {
    valeur: "confidentielle",
    label: "Confidentielle",
    variante: "danger",
    icone: ShieldAlert,
    description:
      "Les rôles désignés, et uniquement les utilisateurs nommés dans la liste blanche.",
  },
];

const NIVEAU_PAR_VALEUR = Object.fromEntries(
  NIVEAUX_CONFIDENTIALITE.map((niveau) => [niveau.valeur, niveau])
);

const NIVEAU_DEFAUT = NIVEAU_PAR_VALEUR.interne;

/**
 * Décrit un niveau de confidentialité.
 *
 * @param {string} [valeur] Niveau tel que renvoyé par l'API.
 * @returns {{valeur: string, label: string, variante: string, icone: object, description: string}}
 */
export function niveauConfidentialite(valeur) {
  return NIVEAU_PAR_VALEUR[valeur] ?? { ...NIVEAU_DEFAUT, valeur: valeur ?? null };
}

/** Vrai si le document n'est pas lisible par tout utilisateur du module. */
export function estClasse(niveau) {
  return niveau === "restreinte" || niveau === "confidentielle";
}

/** État d'indexation d'un document. */
export function statutIndexation(statut) {
  switch (statut) {
    case "indexe":
      return { label: "Indexé", variante: "success", pastille: true };
    case "echec":
      return {
        label: "Échec d'extraction",
        variante: "danger",
        pastille: true,
      };
    case "en_attente":
      return { label: "En attente", variante: "info", pastille: true };
    default:
      return { label: statut ?? "—", variante: "neutral", pastille: false };
  }
}

/**
 * Icône associée à une extension de document.
 *
 * @param {string} extension Extension sans point, en minuscules.
 * @returns {object} Composant Lucide.
 */
export function iconeDocument(extension) {
  switch (String(extension || "").toLowerCase()) {
    case "pdf":
    case "txt":
    case "md":
      return FileText;
    case "csv":
    case "xlsx":
      return FileSpreadsheet;
    case "json":
      return FileJson;
    default:
      return FileType;
  }
}

/** Liste des extensions reconnues, pour l'affichage. */
export function libellesFormats(formats = []) {
  if (!Array.isArray(formats) || formats.length === 0) return "—";
  return formats.map((format) => `.${format}`).join(", ");
}

/** Modes de réponse possibles du pipeline documentaire. */
const MODES_REPONSE = {
  llm: {
    label: "Réponse fondée sur les extraits",
    variante: "success",
  },
  absence: {
    label: "Aucune source autorisée — modèle non appelé",
    variante: "neutral",
  },
  repli_modele_indisponible: {
    label: "Modèle indisponible — restitution des extraits",
    variante: "warning",
  },
  repli_controle_echoue: {
    label: "Réponse du modèle rejetée — restitution des extraits",
    variante: "warning",
  },
  sans_question: {
    label: "Question vide",
    variante: "neutral",
  },
};

/**
 * Décrit le chemin réellement parcouru par une question.
 *
 * Le mode est la seule chose qui distingue « le modèle a répondu » de « le
 * modèle n'a pas été appelé » : l'interface doit le montrer, sinon un chemin
 * de repli se lit comme une réponse ordinaire.
 *
 * @param {string} [mode]
 */
export function modeReponse(mode) {
  return (
    MODES_REPONSE[mode] ?? {
      label: mode ?? "—",
      variante: "neutral",
    }
  );
}

/** Explication d'un mode, pour le détail du calcul. */
export function explicationMode(mode) {
  switch (mode) {
    case "llm":
      return "Des extraits autorisés dépassaient le seuil : le modèle a rédigé à partir de ce seul contexte, puis chaque affirmation a été rattachée à une source fournie.";
    case "absence":
      return "Aucun extrait autorisé n'a atteint le seuil de pertinence. Le modèle n'a pas été appelé : l'information est déclarée introuvable dans les documents disponibles.";
    case "repli_modele_indisponible":
      return "Le modèle n'a pas pu être joint. Les extraits retenus sont restitués tels quels, sans rédaction.";
    case "repli_controle_echoue":
      return "La réponse produite citait une source inexistante ou avançait un chiffre absent des extraits. Elle a été écartée au profit des extraits, rédigés par le code.";
    case "sans_question":
      return "Aucune question n'a été transmise : aucune recherche n'a été lancée.";
    default:
      return null;
  }
}

/** Décrit le moteur d'embeddings tel que configuré côté backend. */
export function descriptionEmbeddings(embeddings) {
  if (!embeddings || typeof embeddings !== "object") return "—";
  const modele = embeddings.modele || embeddings.model || "";
  const dimension = embeddings.dimension ?? embeddings.dimensions;

  const morceaux = [];
  if (modele) morceaux.push(modele);
  if (dimension) morceaux.push(`${dimension} dimensions`);
  if (embeddings.distance) morceaux.push(embeddings.distance);
  if (embeddings.entrainement) morceaux.push(embeddings.entrainement);
  return morceaux.length > 0 ? morceaux.join(" · ") : "—";
}
