// Libellés et aides de l'écran d'administration.
//
// Les données RBAC (rôles, modules, permissions) vivent dans `lib/permissions.js`
// et sont générées depuis le backend : ce fichier ne les duplique pas, il se
// contente de les rendre lisibles. Ajouter une permission côté backend impose de
// régénérer `lib/permissions.js` ; seul le nommage humain se règle ici.

import { MODULES, PERMISSIONS, PERMISSIONS_PAR_ROLE, ROLES } from "@/lib/permissions";

/** Libellé d'affichage d'un module. */
export const MODULES_LABELS = {
  dashboard: "Tableau de bord",
  beneficiaires: "Bénéficiaires",
  budget: "Budget RFM",
  remboursements: "Remboursements",
  analyses: "Analyses",
  anomalies: "Anomalies",
  previsions: "Prévisions",
  simulations: "Simulations",
  assistant: "Assistant IA",
  documents: "Documents",
  rapports: "Rapports",
  utilisateurs: "Utilisateurs",
  importation: "Importation",
};

/** Ce que le module permet réellement de faire, en une phrase. */
export const MODULES_DESCRIPTIONS = {
  dashboard: "Consulter la synthèse de la plateforme.",
  beneficiaires:
    "Parcourir la population bénéficiaire et enrudenter les fiches.",
  budget: "Suivre le budget RFM alloué, engagé et exécuté.",
  remboursements: "Instruire les dossiers de remboursement.",
  analyses: "Produire les analyses statistiques et temporelles.",
  anomalies: "Détecter puis traiter les anomalies de gestion.",
  previsions: "Générer des prévisions par modèle de série.",
  simulations: "Simuler l'impact d'un scénario budgétaire.",
  assistant: "Interroger les données et les documents en langage naturel.",
  documents: "Déposer, classer, indexer et rechercher les documents.",
  rapports: "Générer et exporter les rapports de pilotage.",
  utilisateurs: "Administrer les comptes, rôles et habilitations.",
  importation: "Importer les données sources de la plateforme.",
};

/** Libellé d'une action, par suffixe de permission. */
export const ACTIONS_LABELS = {
  voir: "voir",
  creer: "créer",
  modifier: "modifier",
  supprimer: "supprimer",
  exporter: "exporter",
  valider: "valider",
  traiter: "traiter",
  generer: "générer",
  utiliser: "utiliser",
  televerser: "téléverser",
  telecharger: "télécharger",
  indexer: "indexer",
  acces: "gérer les accès",
  voir_rapport: "voir les rapports d'import",
  importer: "importer",
  changer_role: "changer un rôle",
};

/** Intention d'un rôle, affichée sous son nom dans la matrice. */
export const ROLES_INTENTS = {
  ADMIN: "Accès complet, y compris l'administration des comptes.",
  RESPONSABLE:
    "Encadre les modules de gestion, sans pouvoir créer ni supprimer de comptes.",
  ANALYSTE: "Produit les analyses et les prévisions, en lecture sur la gestion.",
  AGENT: "Saisit les données et consulte les documents autorisés.",
};

export function libelleModule(module) {
  return MODULES_LABELS[module] ?? module;
}

export function descriptionModule(module) {
  return MODULES_DESCRIPTIONS[module] ?? "";
}

export function libelleAction(permission) {
  const suffixe = String(permission).split(":")[1] ?? "";
  return ACTIONS_LABELS[suffixe] ?? suffixe.replace(/_/g, " ");
}

/** Toutes les permissions d'un module, triées par ordre alphabétique. */
export function permissionsDuModule(module) {
  return PERMISSIONS.filter((permission) => permission.startsWith(`${module}:`)).sort();
}

/** Actions accordées à un rôle sur un module. */
export function actionsRoleModule(role, module) {
  const accordees = PERMISSIONS_PAR_ROLE[role] ?? [];
  return permissionsDuModule(module).filter((permission) =>
    accordees.includes(permission)
  );
}

/** Nombre total de permissions accordées à un rôle. */
export function totalPermissionsRole(role) {
  return (PERMISSIONS_PAR_ROLE[role] ?? []).length;
}

/**
 * Répartition des permissions accordées par rôle.
 *
 * Volontairement sans le nom des agents : un tableau de bord d'administration
 * décrit ce que la plateforme permet, pas qui l'utilise. La liste nominative
 * vit sur la page Utilisateurs, qui exige `utilisateurs:voir`.
 */
export function couvertureParRole() {
  return ROLES.map((role) => ({
    role,
    accordees: totalPermissionsRole(role),
    total: PERMISSIONS.length,
    modules: MODULES.filter(
      (module) => actionsRoleModule(role, module).length > 0
    ),
  }));
}

/**
 * Recherche un compte dans la liste déjà chargée.
 *
 * Le backend n'expose pas de recherche textuelle sur les comptes : le filtre est
 * donc appliqué ici, sur la page courante seulement. Un terme qui ne « trouve »
 * rien peut signifier « absent de cette page » plutôt qu'« inexistant » — d'où
 * l'absence d'asservissement de la pagination à la recherche, qui laisserait
 * croire à un exhaustivité.
 */
export function correspondUtilisateur(utilisateur, terme) {
  if (!terme) return true;
  const cible = terme.trim().toLowerCase();
  if (!cible) return true;
  return [utilisateur.prenom, utilisateur.nom, utilisateur.email, utilisateur.role]
    .filter(Boolean)
    .some((champ) => String(champ).toLowerCase().includes(cible));
}

/** Libellé « Prénom Nom », avec repli sur l'e-mail si l'identité est absente. */
export function nomComplet(utilisateur) {
  if (!utilisateur) return "—";
  const nom = [utilisateur.prenom, utilisateur.nom].filter(Boolean).join(" ").trim();
  return nom || utilisateur.email || "—";
}

/**
 * Un changement de rôle est-il sans effet, donc à ne pas proposer ?
 *
 * Trois cas renvoient `true` : aucun rôle choisi, aucune fiche visée, et le
 * rôle choisi qui est déjà celui de la fiche.
 *
 * Le deuxième cas est celui qui compte. La modale de réattribution conserve le
 * rôle sélectionné après fermeture — elle ne le remet à zéro qu'à l'ouverture.
 * Une fiche refermée laisse donc un rôle résiduel en mémoire face à
 * `utilisateur === null` ; sans ce test, l'écran conclurait qu'il y a un écart
 * à montrer, alors que l'écart se calcule sur une fiche absente. Les enfants de
 * la modale sont construits avant qu'elle ne décide de ne rien afficher, donc
 * l'exception surviendrait même sur une modale fermée.
 */
export function roleSansEffet(role, utilisateur) {
  if (!role || !utilisateur) return true;
  return role === utilisateur.role;
}
