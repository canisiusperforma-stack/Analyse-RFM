"use client";

import { AlertTriangle, Ban } from "lucide-react";

import Badge from "@/components/ui/Badge";
import Button from "@/components/ui/Button";
import Modal from "@/components/ui/Modal";
import { ROLE_BADGE_VARIANTS, ROLE_LABELS, MODULES } from "@/lib/permissions";
import { actionsRoleModule, nomComplet } from "@/lib/administration";

/**
 * Confirmation de suppression.
 *
 * La suppression est définitive et irréversible : pas de corbeille, pas
 * d'historique, pas de restitution. Le mot « désactivation » n'est donc pas
 * proposé comme équivalent — il ne l'est pas. Désactiver conserve le compte et
 * son historique, et se refait en un clic ; la présente action, elle, ne se
 * reprend pas.
 *
 * Le nombre de modules concernés est affiché parce qu'il est l'indicateur le
 * plus immédiat de ce qui disparaît avec le compte. Il vient du référentiel, et
 * non d'un calcul : le backend peut refuser l'attribution d'un rôle dont
 * certaines actions ne seraient pas effectives.
 */
export default function SuppressionModal({
  open = false,
  utilisateur = null,
  onClose,
  onConfirm,
  submitting = false,
}) {
  if (!utilisateur) return null;

  const modulesOuverts = MODULES.filter(
    (module) => actionsRoleModule(utilisateur.role, module).length > 0
  );

  return (
    <Modal
      open={open}
      onClose={onClose}
      size="sm"
      title="Supprimer le compte"
      description="Cette action est définitive et ne peut pas être annulée."
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={submitting}>
            Annuler
          </Button>
          <Button variant="danger" onClick={onConfirm} loading={submitting}>
            <Ban size={15} aria-hidden="true" />
            Supprimer définitivement
          </Button>
        </>
      }
    >
      <div className="admin-suppression">
        <div className="admin-suppression__cible">
          <span className="admin-suppression__nom">{nomComplet(utilisateur)}</span>
          <span className="admin-suppression__email">{utilisateur.email}</span>
          <Badge variant={ROLE_BADGE_VARIANTS[utilisateur.role] ?? "neutral"}>
            {ROLE_LABELS[utilisateur.role] ?? utilisateur.role}
          </Badge>
        </div>

        <div className="alert alert--error admin-suppression__alerte">
          <AlertTriangle size={18} className="alert__icon" aria-hidden="true" />
          <span>
            Le compte, son rôle et ses habilitations seront effacés. Les
            documents, analyses et données qu&apos;il a produits ne sont pas
            concernés : ils appartiennent à la plateforme, pas au compte.
          </span>
        </div>

        {modulesOuverts.length > 0 && (
          <p className="text-muted">
            Ce compte dispose actuellement d&apos;accès à{" "}
            {modulesOuverts.length} module(s). Pour couper l&apos;accès sans
            perdre la trace du compte, préférez la désactivation.
          </p>
        )}
      </div>
    </Modal>
  );
}
