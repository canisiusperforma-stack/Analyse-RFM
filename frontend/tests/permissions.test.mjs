// Tests du référentiel de permissions frontend (affichage uniquement).
//
// Le backend est la seule source d'autorité ; la matrice du frontend est
// générée depuis backend/app/services/permission_service.py via :
//   python backend/scripts/generer_permissions_frontend.py
// Ces tests pinent la projection générée pour chaque rôle.
//
// Lancement : npm test  (node --test tests/)

import { test, describe } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const source = readFileSync(
  path.join(__dirname, "..", "lib", "permissions.js"),
  "utf8"
);
const mod = await import(
  "data:text/javascript;base64," + Buffer.from(source).toString("base64")
);

const {
  ROLES,
  ROLE_DEFAUT,
  MODULES,
  PERMISSIONS,
  PERMISSIONS_PAR_ROLE,
  roleValide,
  permissionsDuRole,
  estPermissionValide,
  aLaPermission,
  aUneDesPermissions,
  aToutesLesPermissions,
  moduleAccessible,
  modulesAccessibles,
  modulePourRoute,
  permissionsEffectives,
  estRoutePublique,
} = mod;

const ATTENDUES = {
  ADMIN: [
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
    "utilisateurs:voir",
  ],
  RESPONSABLE: [
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
    "utilisateurs:voir",
  ],
  ANALYSTE: [
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
    "simulations:voir",
  ],
  AGENT: [
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
    "simulations:voir",
  ],
};

function ensemble(valeurs) {
  return new Set(valeurs);
}

describe("RBAC frontend : référentiel", () => {
  test("rôles et rôle par défaut", () => {
    assert.deepEqual(
      ensemble(ROLES),
      ensemble(["ADMIN", "RESPONSABLE", "ANALYSTE", "AGENT"])
    );
    assert.equal(ROLE_DEFAUT, "AGENT");
    for (const role of ROLES) {
      assert.ok(roleValide(role));
    }
    assert.ok(!roleValide("INCONNU"));
    assert.ok(!roleValide(null));
  });

  test("modules couvrent les 13 modules", () => {
    assert.deepEqual(
      ensemble(MODULES),
      ensemble([
        "dashboard",
        "beneficiaires",
        "budget",
        "remboursements",
        "analyses",
        "anomalies",
        "previsions",
        "simulations",
        "assistant",
        "documents",
        "rapports",
        "utilisateurs",
        "importation",
      ])
    );
  });

  test("chaque permission est rattachée à un module déclaré", () => {
    const modules = new Set(MODULES);
    for (const permission of PERMISSIONS) {
      const [module] = permission.split(":", 1);
      assert.ok(modules.has(module), `Permission hors module : ${permission}`);
    }
  });

  test("chaque permission déclarée est attribuée à au moins un rôle", () => {
    const couvertes = new Set();
    for (const role of ROLES) {
      for (const permission of PERMISSIONS_PAR_ROLE[role]) {
        couvertes.add(permission);
      }
    }
    assert.deepEqual(couvertes, new Set(PERMISSIONS));
  });

  test("matrice générée == attentes pour chaque rôle", () => {
    for (const role of ROLES) {
      assert.deepEqual(
        ensemble(PERMISSIONS_PAR_ROLE[role]),
        ensemble(ATTENDUES[role]),
        role
      );
      assert.deepEqual(ensemble(permissionsDuRole(role)), ensemble(ATTENDUES[role]));
    }
    assert.deepEqual(permissionsDuRole("INCONNU"), []);
    assert.deepEqual(permissionsDuRole(null), []);
  });
});

describe("RBAC frontend : chaque rôle", () => {
  test("ADMIN : accès total", () => {
    const perms = PERMISSIONS_PAR_ROLE.ADMIN;
    for (const permission of PERMISSIONS) {
      assert.ok(
        aLaPermission(perms, permission),
        `ADMIN doit avoir ${permission}`
      );
    }
    for (const module of MODULES) {
      assert.ok(moduleAccessible(perms, module));
    }
  });

  test("RESPONSABLE : pilotage complet sans gestion des utilisateurs", () => {
    const perms = PERMISSIONS_PAR_ROLE.RESPONSABLE;
    assert.ok(aLaPermission(perms, "remboursements:valider"));
    assert.ok(aLaPermission(perms, "simulations:supprimer"));
    assert.ok(aLaPermission(perms, "importation:importer"));
    assert.ok(aLaPermission(perms, "utilisateurs:voir"));
    assert.ok(!aLaPermission(perms, "utilisateurs:creer"));
    assert.ok(!aLaPermission(perms, "utilisateurs:modifier"));
    assert.ok(!aLaPermission(perms, "utilisateurs:supprimer"));
    assert.ok(!aLaPermission(perms, "utilisateurs:changer_role"));
  });

  test("ANALYSTE : lecture, analyse, prévisions, simulations, rapports", () => {
    const perms = PERMISSIONS_PAR_ROLE.ANALYSTE;
    assert.ok(aLaPermission(perms, "previsions:creer"));
    assert.ok(aLaPermission(perms, "simulations:creer"));
    assert.ok(aLaPermission(perms, "rapports:generer"));
    assert.ok(aLaPermission(perms, "anomalies:traiter"));
    assert.ok(aLaPermission(perms, "importation:voir_rapport"));
    assert.ok(!aLaPermission(perms, "beneficiaires:modifier"));
    assert.ok(!aLaPermission(perms, "documents:televerser"));
    assert.ok(!aLaPermission(perms, "remboursements:valider"));
    assert.ok(!moduleAccessible(perms, "utilisateurs"));
  });

  test("AGENT : opérationnel sans validation ni gestion", () => {
    const perms = PERMISSIONS_PAR_ROLE.AGENT;
    assert.ok(aLaPermission(perms, "remboursements:creer"));
    assert.ok(aLaPermission(perms, "beneficiaires:modifier"));
    assert.ok(aLaPermission(perms, "assistant:utiliser"));
    assert.ok(aLaPermission(perms, "importation:importer"));
    assert.ok(!aLaPermission(perms, "beneficiaires:supprimer"));
    assert.ok(!aLaPermission(perms, "remboursements:valider"));
    assert.ok(!aLaPermission(perms, "importation:voir_rapport"));
    assert.ok(!aLaPermission(perms, "rapports:generer"));
    assert.ok(!moduleAccessible(perms, "utilisateurs"));
  });

  test("accès par module attendu pour chaque rôle", () => {
    const attendus = {
      ADMIN: new Set(MODULES),
      RESPONSABLE: new Set(MODULES),
      ANALYSTE: new Set(MODULES).difference(new Set(["utilisateurs"])),
      AGENT: new Set(MODULES).difference(new Set(["utilisateurs"])),
    };
    for (const role of ROLES) {
      const perms = PERMISSIONS_PAR_ROLE[role];
      assert.deepEqual(
        new Set(modulesAccessibles(perms)),
        attendus[role],
        role
      );
    }
  });
});

describe("RBAC frontend : helpers et gardes", () => {
  test("aLaPermission / aUneDesPermissions / aToutesLesPermissions", () => {
    const perms = ["dashboard:voir", "rapports:generer"];
    assert.ok(aLaPermission(perms, "dashboard:voir"));
    assert.ok(!aLaPermission(perms, "rapports:exporter"));
    assert.ok(!aLaPermission(perms, "module:inconnue"));
    assert.ok(!estPermissionValide("module:inconnue"));
    assert.ok(aUneDesPermissions(perms, ["rapports:exporter", "rapports:generer"]));
    assert.ok(
      aToutesLesPermissions(perms, ["dashboard:voir", "rapports:generer"])
    );
    assert.ok(!aToutesLesPermissions(perms, ["dashboard:voir", "rapports:exporter"]));
  });

  test("modulePourRoute et routes publiques", () => {
    assert.equal(modulePourRoute("/dashboard"), "dashboard");
    assert.equal(modulePourRoute("/analyses/anomalies"), "anomalies");
    assert.equal(modulePourRoute("/analyses"), "analyses");
    assert.equal(modulePourRoute("/administration/utilisateurs"), "utilisateurs");
    assert.equal(modulePourRoute("/imports"), "importation");
    assert.equal(modulePourRoute("/inconnu"), null);
    assert.ok(estRoutePublique("/connexion"));
    assert.ok(estRoutePublique("/"));
    assert.ok(estRoutePublique("/403"));
    assert.ok(!estRoutePublique("/dashboard"));
  });

  test("permissionsEffectives : serveur prioritaire, repli par rôle", () => {
    assert.deepEqual(
      permissionsEffectives({
        role: "AGENT",
        permissions: ["dashboard:voir", "rapports:exporter", "divers:bogus"],
      }),
      ["dashboard:voir", "rapports:exporter"]
    );
    assert.deepEqual(
      permissionsEffectives({ role: "ANALYSTE" }),
      [...PERMISSIONS_PAR_ROLE.ANALYSTE]
    );
    assert.deepEqual(permissionsEffectives(null), []);
  });
});