"use client";

import { useEffect, useMemo, useState } from "react";
import { ArrowRight, ShieldAlert } from "lucide-react";

import Badge from "@/components/ui/Badge";
import Button from "@/components/ui/Button";
import Modal from "@/components/ui/Modal";
import {
  MODULES,
  ROLE_BADGE_VARIANTS,
  ROLE_LABELS,
  ROLES,
} from "@/lib/permissions";
import {
  ROLES_INTENTS,
  actionsRoleModule,
  descriptionModule,
  libelleAction,
  libelleModule,
  nomComplet,
  roleSansEffet,
} from "@/lib/administration";

/**
 * Réattribution d'un rôle.
 *
 * Le changement est présenté comme ce qu'il est : un écart, avec ce que le rôle
 * cible ajoute et ce qu'il retire. Attribuer `AGENT` à un compte qui était
 * `ADMIN` retire l'accès à l'administration, et lelisting des actions accordées
 * dans les deux colonnes est là pour que ce retrait soit vu *avant* la
 * confirmation — pas découvert à la prochaine ouverture de la plateforme.
 *
 * Le backend interdit l'opération sur le propre compte de l'acteur. L'écran ne
 * propose donc pas ce choix-là : afficher un bouton qui échoue toujours serait
 * du bruit, et laisser croire qu'on peut s'attribuer un rôle serait une faute.
 */
export default function RoleModal({
  open = false,
  utilisateur = null,
  onClose,
  onSubmit,
  submitting = false,
}) {
  const [role, setRole] = useState(null);

  useEffect(() => {
    if (open) setRole(utilisateur?.role ?? null);
  }, [open, utilisateur]);

  const ecart = useMemo(() => {
    if (!role || !utilisateur) return { ajoutes: [], retires: [] };
    const avant = new Set(actionsTousModules(utilisateur.role));
    const apres = new Set(actionsTousModules(role));
    return {
      ajoutes: [...apres].filter((permission) => !avant.has(permission)),
      retires: [...avant].filter((permission) => !apres.has(permission)),
    };
  }, [role, utilisateur]);

  // La garde est dans `roleSansEffet` : `role` survit à la fermeture, et lire
  // `utilisateur.role` sur une fiche refermée planterait à la construction des
  // enfants, avant même que `Modal` ne décide de ne rien afficher.
  const inchange = roleSansEffet(role, utilisateur);

  return (
    <Modal
      open={open}
      onClose={onClose}
      size="lg"
      title={`Rôle de ${nomComplet(utilisateur)}`}
      description="La liste ci-dessous est celle du référentiel backend. Elle explique l'effet de l'attribution ; elle ne l'accorde pas."
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={submitting}>
            Annuler
          </Button>
          <Button
            onClick={() => onSubmit(role)}
            loading={submitting}
            disabled={inchange}
          >
            Attribuer {ROLE_LABELS[role] ?? "…"}
          </Button>
        </>
      }
    >
      <div className="admin-form">
        <div className="admin-roles">
          {ROLES.map((nomRole) => {
            const actif = nomRole === utilisateur?.role;
            const cible = nomRole === role && !actif;
            return (
              <button
                key={nomRole}
                type="button"
                className={`admin-role${cible ? "est-cible" : ""}`}
                onClick={() => setRole(nomRole)}
                aria-pressed={cible || (actif && !role)}
                disabled={submitting}
              >
                <span className="admin-role__entete">
                  <Badge variant={ROLE_BADGE_VARIANTS[nomRole] ?? "neutral"}>
                    {ROLE_LABELS[nomRole] ?? nomRole}
                  </Badge>
                  {actif && (
                    <span className="admin-role__actuel">Rôle actuel</span>
                  )}
                </span>
                <span className="admin-role__intention">
                  {ROLES_INTENTS[nomRole]}
                </span>
              </button>
            );
          })}
        </div>

        {role && !inchange && (
          <div className="admin-ecart">
            <div className="admin-ecart__ligne">
              <Badge variant={ROLE_BADGE_VARIANTS[utilisateur.role] ?? "neutral"}>
                {ROLE_LABELS[utilisateur.role] ?? utilisateur.role}
              </Badge>
              <ArrowRight size={16} aria-hidden="true" />
              <Badge variant={ROLE_BADGE_VARIANTS[role] ?? "neutral"}>
                {ROLE_LABELS[role] ?? role}
              </Badge>
            </div>

            <div className="admin-ecart__colonnes">
              <EcartColonne
                titre="Droits retirés"
                permissions={ecart.retires}
                vide="Aucun droit perdu."
              />
              <EcartColonne
                titre="Droits ajoutés"
                permissions={ecart.ajoutes}
                vide="Aucun droit nouveau."
                positif
              />
            </div>

            {(ecart.ajoutes.length > 0 || ecart.retires.length > 0) && (
              <p className="admin-ecart__alerte">
                <ShieldAlert size={14} aria-hidden="true" />
                {ecart.retires.length > ecart.ajoutes.length
                  ? "Le compte perdra l'accès à des modules. Ses jetons en cours restent valables jusqu'à expiration."
                  : "Le compte gagnera des droits. L'attribution est immédiate et ne demande pas de reconnexion."}
              </p>
            )}
          </div>
        )}
      </div>
    </Modal>
  );
}

/** Actions accordées par un rôle, tous modules confondus. */
function actionsTousModules(role) {
  if (!role) return [];
  return MODULES.flatMap((module) => actionsRoleModule(role, module));
}

function EcartColonne({ titre, permissions, vide, positif = false }) {
  const groupes = useMemo(() => {
    const parModule = new Map();
    permissions.forEach((permission) => {
      const [module, suffixe] = permission.split(":");
      if (!parModule.has(module)) parModule.set(module, []);
      parModule.get(module).push(suffixe);
    });
    return [...parModule.entries()];
  }, [permissions]);

  return (
    <div className="admin-ecart__colonne">
      <span className="admin-ecart__titre">{titre}</span>
      {permissions.length === 0 ? (
        <p className="text-muted">{vide}</p>
      ) : (
        <ul className="admin-ecart__liste">
          {groupes.map(([module, suffixes]) => (
            <li key={module}>
              <span className="admin-ecart__module">
                {libelleModule(module)}
                <small>{descriptionModule(module)}</small>
              </span>
              <span className="admin-ecart__actions">
                {suffixes.map((permission) => (
                  <span
                    key={permission}
                    className={`admin-perm admin-perm--${positif ? "ajout" : "retrait"}`}
                  >
                    {libelleAction(`${module}:${permission}`)}
                  </span>
                ))}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
