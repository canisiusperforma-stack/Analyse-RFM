"use client";

import { useMemo, useState } from "react";
import { Info, ShieldCheck } from "lucide-react";

import Badge from "@/components/ui/Badge";
import Select from "@/components/ui/Select";
import { MODULES, ROLE_BADGE_VARIANTS, ROLE_LABELS, ROLES } from "@/lib/permissions";
import {
  actionsRoleModule,
  descriptionModule,
  libelleAction,
  libelleModule,
  permissionsDuModule,
} from "@/lib/administration";

/**
 * Matrice des habilitations : module × rôle.
 *
 * Elle est tirée du référentiel généré depuis
 * `backend/app/services/permission_service.py`, et non du backend à chaque
 * affichage. Ce n'est pas un raccourci : c'est la seule façon de montrer des
 * droits *sans* possède les avoir. Un·e responsable ne peut pas lister les
 * comptes, mais il lui revient de savoir ce que vaut chaque rôle — sinon comment
 * demander une habilitation qu'on ne sait pas nommer ?
 *
 * En revanche, la matrice n'accorde rien. Elle explique ; elle n'autorise pas.
 * Le backend reste seul juge, et un droit affiché ici peut avoir été modifié
 * depuis le déploiement du frontend. La note sous le tableau le dit.
 */
export default function MatricePermissions() {
  const [roleFocus, setRoleFocus] = useState("");

  const modules = useMemo(
    () =>
      MODULES.map((module) => ({
        module,
        actions: permissionsDuModule(module),
        parRole: Object.fromEntries(
          ROLES.map((role) => [role, actionsRoleModule(role, module)])
        ),
      })).filter((entree) => entree.actions.length > 0),
    []
  );

  return (
    <section className="card" id="roles">
      <div className="card__header">
        <span className="conv-section__icon">
          <ShieldCheck size={18} />
        </span>
        <div>
          <h3 className="card__title">Rôles et habilitations</h3>
          <p className="text-muted">
            Ce que vaut chaque rôle, module par module. Lecture seule : les
            habilitations sont attribuées sur la page Utilisateurs.
          </p>
        </div>
      </div>

      <div className="card__body">
        <div className="admin-matrice__barre">
          <Select
            label="Isoler un rôle"
            value={roleFocus}
            onChange={(evenement) => setRoleFocus(evenement.target.value)}
            placeholder="Les quatre rôles"
            options={ROLES.map((role) => ({
              value: role,
              label: ROLE_LABELS[role] ?? role,
            }))}
          />
          {roleFocus && (
            <p className="text-muted admin-matrice__legende">
              <Info size={13} aria-hidden="true" /> Les colonnes autres que{" "}
              {ROLE_LABELS[roleFocus]} sont atténuées pour permettre la
              comparaison.
            </p>
          )}
        </div>

        <div className="table-wrap">
          <table className="table admin-matrice">
            <thead>
              <tr>
                <th scope="col">Module</th>
                {ROLES.map((role) => (
                  <th
                    key={role}
                    scope="col"
                    className={roleFocus && roleFocus !== role ? "est-attenuee" : undefined}
                  >
                    <Badge variant={ROLE_BADGE_VARIANTS[role] ?? "neutral"}>
                      {ROLE_LABELS[role] ?? role}
                    </Badge>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {modules.map(({ module, actions, parRole }) => (
                <tr key={module}>
                  <th scope="row" className="admin-matrice__module">
                    <span className="tableau__nom">{libelleModule(module)}</span>
                    <span className="tableau__sous-texte" style={{ display: "block" }}>
                      {descriptionModule(module)}
                    </span>
                  </th>
                  {ROLES.map((role) => {
                    const accordees = parRole[role] ?? [];
                    const attenuee = roleFocus && roleFocus !== role;
                    return (
                      <td
                        key={role}
                        className={attenuee ? "est-attenuee" : undefined}
                        aria-label={`${ROLE_LABELS[role] ?? role} sur ${libelleModule(module)} : ${
                          accordees.length
                        } action(s) sur ${actions.length}`}
                      >
                        <div className="admin-matrice__actions">
                          {accordees.length === 0 && (
                            <span className="admin-perm admin-perm--vide" aria-hidden="true">
                              —
                            </span>
                          )}
                          {accordees.map((permission) => (
                            <span key={permission} className="admin-perm">
                              {libelleAction(permission)}
                            </span>
                          ))}
                        </div>
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <p className="text-muted admin-matrice__note">
          <Info size={13} aria-hidden="true" /> Cette matrice est une
          description, pas une autorisation. Elle provient du même code que le
          backend, mais un droit peut avoir changé depuis le déploiement du
          frontend : en cas d&apos;écart, l&apos;API fait foi et l&apos;écran
          n&apos;annonce que ce qu&apos;elle a réussi à obtenir.
        </p>
      </div>
    </section>
  );
}
