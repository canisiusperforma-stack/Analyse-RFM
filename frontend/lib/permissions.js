// Permissions frontend (affichage uniquement).
//
// La sécurité repose exclusivement sur le backend (source d'autorité) :
//   backend/app/services/permission_service.py
// Les données RBAC du bloc ci-dessous sont régénérées depuis le backend :
//   python backend/scripts/generer_permissions_frontend.py
// Le frontend ne doit JAMAIS être considéré comme une protection : il ne
// sert qu'à masquer/afficher les fonctionnalités selon les permissions.
// Voir aussi : hooks/usePermissions.js, components/auth/RequirePermission.jsx,
//              components/auth/PermissionsGate.jsx.

export const ROLE_LABELS = {
  ADMIN: "Administrateur",
  RESPONSABLE: "Responsable",
  ANALYSTE: "Analyste",
  AGENT: "Agent",
};

export const ROLE_BADGE_VARIANTS = {
  ADMIN: "danger",
  RESPONSABLE: "warning",
  ANALYSTE: "primary",
  AGENT: "neutral",
};

//RBAC_DONNEES_DEBUT
// Données générées automatiquement — source d'autorité :

// backend/app/services/permission_service.py. Ne pas modifier à la main.

export const ROLES = [
    "ADMIN",
    "AGENT",
    "ANALYSTE",
    "RESPONSABLE"
  ];

export const ROLE_DEFAUT = "AGENT";

export const MODULES = [
    "analyses",
    "anomalies",
    "assistant",
    "beneficiaires",
    "budget",
    "dashboard",
    "documents",
    "importation",
    "previsions",
    "rapports",
    "remboursements",
    "simulations",
    "utilisateurs"
  ];

export const PERMISSIONS = [
    "analyses:exporter",
    "analyses:voir",
    "anomalies:traiter",
    "anomalies:voir",
    "assistant:utiliser",
    "beneficiaires:creer",
    "beneficiaires:exporter",
    "beneficiaires:modifier",
    "beneficiaires:supprimer",
    "beneficiaires:voir",
    "budget:creer",
    "budget:exporter",
    "budget:modifier",
    "budget:supprimer",
    "budget:voir",
    "dashboard:voir",
    "documents:acces",
    "documents:indexer",
    "documents:supprimer",
    "documents:telecharger",
    "documents:televerser",
    "documents:voir",
    "importation:importer",
    "importation:voir_rapport",
    "previsions:creer",
    "previsions:exporter",
    "previsions:voir",
    "rapports:exporter",
    "rapports:generer",
    "rapports:voir",
    "remboursements:creer",
    "remboursements:exporter",
    "remboursements:modifier",
    "remboursements:supprimer",
    "remboursements:valider",
    "remboursements:voir",
    "simulations:creer",
    "simulations:exporter",
    "simulations:supprimer",
    "simulations:voir",
    "utilisateurs:changer_role",
    "utilisateurs:creer",
    "utilisateurs:modifier",
    "utilisateurs:supprimer",
    "utilisateurs:voir"
  ];

export const PERMISSIONS_PAR_ROLE = {

  "ADMIN": [
    "analyses:exporter",
    "analyses:voir",
    "anomalies:traiter",
    "anomalies:voir",
    "assistant:utiliser",
    "beneficiaires:creer",
    "beneficiaires:exporter",
    "beneficiaires:modifier",
    "beneficiaires:supprimer",
    "beneficiaires:voir",
    "budget:creer",
    "budget:exporter",
    "budget:modifier",
    "budget:supprimer",
    "budget:voir",
    "dashboard:voir",
    "documents:acces",
    "documents:indexer",
    "documents:supprimer",
    "documents:telecharger",
    "documents:televerser",
    "documents:voir",
    "importation:importer",
    "importation:voir_rapport",
    "previsions:creer",
    "previsions:exporter",
    "previsions:voir",
    "rapports:exporter",
    "rapports:generer",
    "rapports:voir",
    "remboursements:creer",
    "remboursements:exporter",
    "remboursements:modifier",
    "remboursements:supprimer",
    "remboursements:valider",
    "remboursements:voir",
    "simulations:creer",
    "simulations:exporter",
    "simulations:supprimer",
    "simulations:voir",
    "utilisateurs:changer_role",
    "utilisateurs:creer",
    "utilisateurs:modifier",
    "utilisateurs:supprimer",
    "utilisateurs:voir"
  ],

  "AGENT": [
    "analyses:voir",
    "anomalies:voir",
    "assistant:utiliser",
    "beneficiaires:creer",
    "beneficiaires:modifier",
    "beneficiaires:voir",
    "budget:voir",
    "dashboard:voir",
    "documents:telecharger",
    "documents:televerser",
    "documents:voir",
    "importation:importer",
    "previsions:voir",
    "rapports:voir",
    "remboursements:creer",
    "remboursements:modifier",
    "remboursements:voir",
    "simulations:voir"
  ],

  "ANALYSTE": [
    "analyses:exporter",
    "analyses:voir",
    "anomalies:traiter",
    "anomalies:voir",
    "assistant:utiliser",
    "beneficiaires:exporter",
    "beneficiaires:voir",
    "budget:exporter",
    "budget:voir",
    "dashboard:voir",
    "documents:telecharger",
    "documents:voir",
    "importation:voir_rapport",
    "previsions:creer",
    "previsions:exporter",
    "previsions:voir",
    "rapports:exporter",
    "rapports:generer",
    "rapports:voir",
    "remboursements:exporter",
    "remboursements:voir",
    "simulations:creer",
    "simulations:exporter",
    "simulations:voir"
  ],

  "RESPONSABLE": [
    "analyses:exporter",
    "analyses:voir",
    "anomalies:traiter",
    "anomalies:voir",
    "assistant:utiliser",
    "beneficiaires:creer",
    "beneficiaires:exporter",
    "beneficiaires:modifier",
    "beneficiaires:supprimer",
    "beneficiaires:voir",
    "budget:creer",
    "budget:exporter",
    "budget:modifier",
    "budget:supprimer",
    "budget:voir",
    "dashboard:voir",
    "documents:indexer",
    "documents:supprimer",
    "documents:telecharger",
    "documents:televerser",
    "documents:voir",
    "importation:importer",
    "importation:voir_rapport",
    "previsions:creer",
    "previsions:exporter",
    "previsions:voir",
    "rapports:exporter",
    "rapports:generer",
    "rapports:voir",
    "remboursements:creer",
    "remboursements:exporter",
    "remboursements:modifier",
    "remboursements:supprimer",
    "remboursements:valider",
    "remboursements:voir",
    "simulations:creer",
    "simulations:exporter",
    "simulations:supprimer",
    "simulations:voir",
    "utilisateurs:voir"
  ],

};
//RBAC_DONNEES_FIN

// -----------------------------------------------
// Routes et modules (gardes de pages côté client).
// -----------------------------------------------

export const ROUTES_PUBLIQUES = ["/", "/connexion", "/403"];

// Module requis pour chaque route applicative.
export const MODULE_PAR_ROUTE = {
  "/dashboard": "dashboard",
  "/beneficiaires": "beneficiaires",
  "/remboursements": "remboursements",
  "/budget": "budget",
  "/analyses/statistiques": "analyses",
  "/analyses/temporelle": "analyses",
  "/analyses/anomalies": "anomalies",
  "/analyses": "analyses",
  "/previsions": "previsions",
  "/simulations": "simulations",
  "/assistant-ia": "assistant",
  "/documents": "documents",
  "/rapports": "rapports",
  "/administration/utilisateurs": "utilisateurs",
  "/administration": "utilisateurs",
  "/imports": "importation",
};

// -----------------------------------------------
// Helpers.
// -----------------------------------------------

export function roleValide(role) {
  return ROLES.includes(role);
}

export function permissionsDuRole(role) {
  if (!roleValide(role)) return [];
  return [...PERMISSIONS_PAR_ROLE[role]];
}

export function estPermissionValide(permission) {
  return PERMISSIONS.includes(permission);
}

export function normaliserPermissions(permissions) {
  if (!Array.isArray(permissions)) return [];
  return [...new Set(permissions.filter((p) => estPermissionValide(p)))];
}

export function aLaPermission(permissions, permission) {
  if (!estPermissionValide(permission)) return false;
  return normaliserPermissions(permissions).includes(permission);
}

export function aUneDesPermissions(permissions, liste) {
  const normalisees = normaliserPermissions(permissions);
  return liste.some((p) => normalisees.includes(p));
}

export function aToutesLesPermissions(permissions, liste) {
  const normalisees = normaliserPermissions(permissions);
  return liste.every((p) => normalisees.includes(p));
}

export function moduleAccessible(permissions, module) {
  if (!MODULES.includes(module)) return false;
  return normaliserPermissions(permissions).some((p) =>
    p.startsWith(`${module}:`)
  );
}

export function modulesAccessibles(permissions) {
  const normalisees = normaliserPermissions(permissions);
  return MODULES.filter((module) =>
    normalisees.some((p) => p.startsWith(`${module}:`))
  );
}

export function modulePourRoute(pathname) {
  const route = typeof pathname === "string" ? pathname : "";
  if (MODULE_PAR_ROUTE[route]) return MODULE_PAR_ROUTE[route];
  const prefixes = Object.keys(MODULE_PAR_ROUTE).sort(
    (a, b) => b.length - a.length
  );
  for (const prefix of prefixes) {
    if (route.startsWith(prefix)) return MODULE_PAR_ROUTE[prefix];
  }
  return null;
}

export function estRoutePublique(pathname) {
  return ROUTES_PUBLIQUES.includes(pathname);
}

// Fusionne les permissions du serveur avec le référentiel local (par rôle)
// pour que l'UI reste cohérente avant la première réponse /auth/me.
// Seul le backend fait foi ; ceci n'est qu'un fallback d'affichage.
export function permissionsEffectives(utilisateur) {
  if (!utilisateur) return [];
  const serveur = normaliserPermissions(utilisateur.permissions);
  if (serveur.length > 0) return serveur;
  return permissionsDuRole(utilisateur.role);
}