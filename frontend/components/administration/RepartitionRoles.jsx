"use client";

import { useMemo } from "react";
import { PieChart } from "lucide-react";

import Loading from "@/components/ui/Loading";
import { ROLE_LABELS } from "@/lib/permissions";
import { formatNumber } from "@/lib/formatters";

/** Teinte de barre, alignée sur la couleur des pastilles de rôle. */
const COULEURS_ROLE = {
  ADMIN: "var(--color-danger)",
  RESPONSABLE: "var(--color-warning)",
  ANALYSTE: "var(--color-primary)",
  AGENT: "var(--color-text-muted)",
};

/**
 * Répartition des comptes par rôle.
 *
 * Elle est calculée sur l'ensemble des comptes, pas sur la page courante, et le
 * dit quand la population dépasse la fenêtre de chargement. Une répartition
 * tronquée sans mention le serait pas : elle laisserait croire à une population
 * répartie alors que l'administrateur n'en verrait qu'une fraction.
 */
export default function RepartitionRoles({ compte, loading }) {
  const barres = useMemo(() => {
    if (!compte || compte.observe === 0) return [];
    const maximum = Math.max(
      ...compte.parRole.map((entree) => entree.total),
      1
    );
    return compte.parRole.map((entree) => ({
      ...entree,
      part: (entree.total / maximum) * 100,
    }));
  }, [compte]);

  if (loading && !compte) return <Loading label="Répartition des rôles…" />;
  if (!compte || compte.observe === 0) return null;

  return (
    <section className="card">
      <div className="card__header">
        <span className="conv-section__icon">
          <PieChart size={18} />
        </span>
        <div>
          <h3 className="card__title">Répartition par rôle</h3>
          <p className="text-muted">
            {compte.partiel
              ? `Sur les ${formatNumber(compte.observe)} comptes les plus anciens.`
              : `Les ${formatNumber(compte.population)} comptes de la plateforme.`}
          </p>
        </div>
      </div>

      <div className="card__body">
        <div className="repartition-list">
          {barres.map(({ role, total, part }) => (
            <div key={role} className="repartition-item">
              <div className="repartition-item__row">
                <span className="repartition-item__label">
                  {ROLE_LABELS[role] ?? role}
                </span>
                <span className="repartition-item__value">
                  {formatNumber(total)}
                  <small>
                    {compte.population > 0
                      ? `${Math.round((total / compte.population) * 100)} %`
                      : "—"}
                  </small>
                </span>
              </div>
              <div className="repartition-item__track">
                <span
                  className="repartition-item__fill"
                  style={{
                    width: `${part}%`,
                    background: COULEURS_ROLE[role] ?? COULEURS_ROLE.AGENT,
                  }}
                />
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
