"use client";

import Link from "next/link";
import { AlertCircle, ServerCrash, UserCog } from "lucide-react";

import PermissionsGate from "@/components/auth/PermissionsGate";
import PageContainer from "@/components/layout/PageContainer";
import EtatPlateforme from "@/components/administration/EtatPlateforme";
import MatricePermissions from "@/components/administration/MatricePermissions";
import PerimetreModules from "@/components/administration/PerimetreModules";
import RepartitionRoles from "@/components/administration/RepartitionRoles";
import Badge from "@/components/ui/Badge";
import Button from "@/components/ui/Button";
import usePlateforme from "@/hooks/usePlateforme";
import useUtilisateurs from "@/hooks/useUtilisateurs";
import { usePermissions } from "@/hooks/usePermissions";
import {
  PERMISSIONS,
  ROLE_BADGE_VARIANTS,
  ROLE_LABELS,
  ROLES,
} from "@/lib/permissions";

/**
 * Référentiel d'administration.
 *
 * Cette page décrit ce que la plateforme est et ce qu'elle autorise ; elle
 * n'accorde rien. La distinction n'est pas cosmétique : la matrice des
 * habilitations est lue par des profils qui n'ont pas les droits de lister les
 * comptes — un responsable doit pouvoir nommer une habilitation pour la
 * demander, sans pouvoir la distribuer. Tout ce qui *attribue* un droit vit sur
 * la page Utilisateurs, qui exige `utilisateurs:voir` et les permissions
 * d'écriture correspondantes.
 *
 * Elle est volontairement exhaustive, y compris sur ce qu'elle ne montre pas :
 * le périmètre liste les treize modules, accessibles ou non, parce qu'un module
 * absent de la barre latérale ne se distingue pas, à l'écran, d'un module
 * inexistant. C'est le seul endroit où l'on peut vérifier qu'une restriction a
 * été voulue.
 */
export default function AdministrationPage() {
  const { role, roleLabel, permissions } = usePermissions();
  const { sante, santeErreur, referentiel, loading, verifier, degrade } =
    usePlateforme();
  const { compte } = useUtilisateurs();

  const apiInjoignable = sante == null && santeErreur != null;

  return (
    <PageContainer
      title="Administration"
      subtitle="Ce que la plateforme autorise, ce qu'elle permet, et dans quel état elle se trouve. Cette page explique ; elle n'accorde aucun droit."
      actions={
        <>
          {role && (
            <Badge variant={ROLE_BADGE_VARIANTS[role] ?? "neutral"} dot>
              {roleLabel ?? ROLE_LABELS[role] ?? role}
            </Badge>
          )}
          <Button
            variant="outline"
            size="sm"
            render={
              <Link href="/administration/utilisateurs">
                <UserCog size={16} aria-hidden="true" />
                Gérer les comptes
              </Link>
            }
          />
        </>
      }
    >
      <div className="import-stack">
        {apiInjoignable && (
          <div className="alert alert--error" role="alert">
            <AlertCircle size={18} className="alert__icon" aria-hidden="true" />
            <span>
              L&apos;API ne répond pas. Tout ce qui suit est affiché à partir du
              référentiel embarqué dans le frontend, et non d&apos;une
              interrogation du serveur : il décrit ce que la plateforme
              autorise, pas ce qu&apos;elle fait actuellement.
            </span>
          </div>
        )}

        {degrade && (
          <div className="alert alert--error" role="alert">
            <ServerCrash size={18} className="alert__icon" aria-hidden="true" />
            <span>
              Mode dégradé : l&apos;API répond, mais la base de données est
              injoignable. Toutes les routes métier échoueront tant que la
              connexion n&apos;est pas rétablie — l&apos;écran reste affiché,
              ce qui ne signifie pas qu&apos;il est utilisable.
            </span>
          </div>
        )}

        <EtatPlateforme
          sante={sante}
          santeErreur={santeErreur}
          referentiel={referentiel}
          loading={loading}
          onVerifier={verifier}
        />

        <PerimetreModules />

        <PermissionsGate permission="utilisateurs:voir">
          <RepartitionRoles compte={compte} loading={false} />
        </PermissionsGate>

        <MatricePermissions />

        <p className="text-muted">
          <AlertCircle size={13} aria-hidden="true" /> Cette page et ses
          composantes s&apos;appuient sur {PERMISSIONS.length} permissions
          déclarées pour {ROLES.length} rôles. Le référentiel est régénéré
          depuis le backend (
          <code>scripts/generer_permissions_frontend.py</code>) : le backend
          reste seul juge, et un droit peut avoir changé depuis le déploiement
          du frontend.
        </p>

        <p className="text-muted">
          Vos {permissions.length} permission(s) effectives proviennent de
          l&apos;API. Elles ne sont pas arbitrées ici : masquer un bouton n&apos;est
          pas une protection, et le backend refuserait l&apos;action de la même
          manière.
        </p>
      </div>
    </PageContainer>
  );
}