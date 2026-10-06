// Tests des aides de l'écran d'administration (lib/administration.js).
//
// Ce fichier ne contient aucune règle d'habilitation : il ne fait que nommer et
// comparer ce que le backend déclare. Les données RBAC qu'il manipule sont
// testées dans permissions.test.mjs.
//
// Le cas couvert ici est une exception qui ne se voyait pas : la modale de
// réattribution conserve le rôle sélectionné après fermeture, et lisait
// `utilisateur.role` sur une fiche refermée. Les enfants de la modale sont
// construits avant qu'elle ne décide de ne rien afficher, donc l'erreur
// survenait même sur une modale fermée.
//
// Lancement : npm test  (node --test tests/)

import { test, describe } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

// `@/lib/...` n'est pas résolvable par Node : on recharge le module via une
// URL data:, comme le fait permissions.test.mjs.
async function chargerAdministration() {
  const permissions = readFileSync(
    path.join(__dirname, "..", "lib", "permissions.js"),
    "utf8"
  );
  const administration = readFileSync(
    path.join(__dirname, "..", "lib", "administration.js"),
    "utf8"
  )
    .replace(
      'from "@/lib/permissions"',
      `from "data:text/javascript;base64,${Buffer.from(permissions).toString(
        "base64"
      )}"`
    );
  return import(
    "data:text/javascript;base64," +
      Buffer.from(administration).toString("base64")
  );
}

const {
  ACTIONS_LABELS,
  MODULES_DESCRIPTIONS,
  MODULES_LABELS,
  ROLES_INTENTS,
  actionsRoleModule,
  correspondUtilisateur,
  couvertureParRole,
  descriptionModule,
  libelleAction,
  libelleModule,
  nomComplet,
  permissionsDuModule,
  roleSansEffet,
  totalPermissionsRole,
} = await chargerAdministration();

describe("administration : changement de rôle", () => {
  const admin = { id: "1", prenom: "Ada", nom: "Ravelo", role: "ADMIN" };

  test("un rôle différent de celui de la fiche est un changement", () => {
    assert.equal(roleSansEffet("AGENT", admin), false);
  });

  test("réattribuer le rôle déjà détenu ne change rien", () => {
    assert.equal(roleSansEffet("ADMIN", admin), true);
  });

  test("aucun rôle choisi ne change rien", () => {
    assert.equal(roleSansEffet(null, admin), true);
  });

  // Le cas qui plantait : rôle résiduel en mémoire, fiche refermée.
  test("un rôle résiduel face à une fiche absente ne change rien", () => {
    assert.equal(roleSansEffet("ADMIN", null), true);
    assert.equal(roleSansEffet("AGENT", undefined), true);
  });

  test("ni rôle ni fiche ne lèvent pas", () => {
    assert.equal(roleSansEffet(null, null), true);
  });
});

describe("administration : identité", () => {
  test("nomComplet assemble prénom et nom", () => {
    assert.equal(nomComplet({ prenom: "Ada", nom: "Ravelo" }), "Ada Ravelo");
  });

  test("nomComplet se replie sur l'e-mail, puis sur un tiret", () => {
    assert.equal(nomComplet({ email: "a@b.c" }), "a@b.c");
    assert.equal(nomComplet({}), "—");
    assert.equal(nomComplet(null), "—");
  });

  test("correspondUtilisateur ignore une chaîne vide", () => {
    const u = { prenom: "Ada", nom: "Ravelo", email: "a@b.c", role: "ADMIN" };
    assert.equal(correspondUtilisateur(u, ""), true);
    assert.equal(correspondUtilisateur(u, "   "), true);
  });

  test("correspondUtilisateur cherche sur l'identité et le rôle", () => {
    const u = { prenom: "Ada", nom: "Ravelo", email: "a@b.c", role: "ADMIN" };
    assert.equal(correspondUtilisateur(u, "ravel"), true);
    assert.equal(correspondUtilisateur(u, "A@B"), true);
    assert.equal(correspondUtilisateur(u, "admin"), true);
    assert.equal(correspondUtilisateur(u, "agent"), false);
  });
});

describe("administration : libellés", () => {
  test("chaque module déclaré a un libellé et une description", () => {
    for (const module of Object.keys(MODULES_LABELS)) {
      assert.ok(MODULES_DESCRIPTIONS[module], `${module} sans description`);
    }
    assert.equal(Object.keys(MODULES_DESCRIPTIONS).length, Object.keys(MODULES_LABELS).length);
  });

  test("libelleAction ne rend que le suffixe de la permission", () => {
    assert.equal(libelleAction("utilisateurs:changer_role"), "changer un rôle");
    assert.equal(libelleAction("budget:voir"), "voir");
  });

  test("un suffixe inconnu reste lisible", () => {
    assert.equal(libelleAction("budget:inventer"), "inventer");
    assert.equal(
      libelleAction("rapports:sous_revenir"),
      "sous revenir"
    );
    assert.equal(libelleAction("budget"), "");
  });

  test("chaque suffixe connu des permissions a un libellé", () => {
    for (const suffixe of Object.keys(ACTIONS_LABELS)) {
      assert.ok(suffixe.length > 0);
    }
  });

  test("chaque rôle a une intention affichée", () => {
    assert.equal(Object.keys(ROLES_INTENTS).length, 4);
  });
});

describe("administration : couverture des rôles", () => {
  test("permissionsDuModule ne renvoie que le module demandé", () => {
    for (const permission of permissionsDuModule("utilisateurs")) {
      assert.ok(permission.startsWith("utilisateurs:"));
    }
  });

  test("un module inconnu ne renvoie aucune permission", () => {
    assert.deepEqual(permissionsDuModule("inexistant"), []);
  });

  test("actionsRoleModule est incluse dans les permissions du module", () => {
    for (const role of ["ADMIN", "RESPONSABLE", "ANALYSTE", "AGENT"]) {
      for (const permission of actionsRoleModule(role, "documents")) {
        assert.ok(permissionsDuModule("documents").includes(permission));
      }
    }
  });

  test("un rôle inconnu n'a aucune permission", () => {
    assert.deepEqual(actionsRoleModule("INCONNU", "documents"), []);
    assert.equal(totalPermissionsRole("INCONNU"), 0);
  });

  test("couvertureParRole est bornée par le total déclaré", () => {
    for (const entree of couvertureParRole()) {
      assert.ok(entree.accordees <= entree.total);
      assert.ok(entree.modules.length > 0, `${entree.role} sans module`);
    }
  });

  test("seul l'administrateur porte la gestion des accès aux documents", () => {
    const parRole = Object.fromEntries(
      couvertureParRole().map((entree) => [entree.role, entree.accordees])
    );
    const total = couvertureParRole()[0].total;
    assert.equal(parRole.ADMIN, total);
    assert.ok(parRole.RESPONSABLE < total);
    assert.ok(parRole.ANALYSTE < total);
    assert.ok(parRole.AGENT < total);
  });
});