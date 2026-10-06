"use client";

import { useMemo } from "react";
import { KeyRound, ShieldCheck, UserCheck, UserX, Users } from "lucide-react";

import StatCard from "@/components/dashboard/StatCard";
import Loading from "@/components/ui/Loading";
import { formatNumber } from "@/lib/formatters";

/**
 * Compteurs d'habilitations.
 *
 * Ils portent sur l'ensemble des comptes, jamais sur la page affichée : un
 * « 2 comptes inactifs » calculé sur vingt lignes serait un hasard. Quand la
 * population dépasse la fenêtre de chargement, le rappel est affiché sous les
 * cartes plutôt que dans une infobulle — c'est la seule façon de ne pas faire
 * passer une estimation pour un compte exact.
 */
export default function UtilisateurStats({ compte, loading }) {
  const inactifs = useMemo(
    () => (compte?.population ? compte.inactifs / compte.population : 0),
    [compte]
  );

  if (loading && !compte) return <Loading label="Chargement des habilitations…" />;
  if (!compte) return null;

  return (
    <div className="dash-section">
      <div className="dash-grid">
        <StatCard
          icon={Users}
          label="Comptes"
          value={formatNumber(compte.population)}
          sub={
            compte.partiel
              ? `décompte sur les ${formatNumber(compte.observe)} premiers`
              : "ensemble de la plateforme"
          }
        />
        <StatCard
          icon={UserCheck}
          label="Comptes actifs"
          value={formatNumber(compte.actifs)}
          variant="success"
          sub={
            compte.actifs > 0
              ? `${formatNumber(Math.round((compte.actifs / compte.population) * 100))} % de la population`
              : "aucun compte actif"
          }
        />
        <StatCard
          icon={UserX}
          label="Comptes désactivés"
          value={formatNumber(compte.inactifs)}
          variant={compte.inactifs > 0 ? "warning" : "default"}
          sub={
            compte.inactifs > 0
              ? `soit ${formatNumber(Math.round(inactifs * 100))} % de la population`
              : "tous les comptes peuvent se connecter"
          }
        />
        <StatCard
          icon={KeyRound}
          label="Jamais connectés"
          value={formatNumber(compte.jamaisConnectes)}
          variant={compte.jamaisConnectes > 0 ? "warning" : "default"}
          sub="comptes actifs sans connexion enregistrée"
        />
      </div>

      {compte.partiel && (
        <p className="text-muted">
          <ShieldCheck size={13} aria-hidden="true" /> La population dépasse la
          fenêtre de chargement : ces compteurs couvrent{" "}
          {formatNumber(compte.observe)} comptes sur {formatNumber(compte.population)}.
        </p>
      )}
    </div>
  );
}
