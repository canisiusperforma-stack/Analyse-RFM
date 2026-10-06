"use client";

import {
  ArrowDownRight,
  ArrowUpRight,
  CalendarRange,
  Coins,
  Gauge,
  Landmark,
  Minus,
  Percent,
  RefreshCcw,
  TrendingUp,
  Wallet,
} from "lucide-react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import StatCard from "@/components/dashboard/StatCard";
import PageContainer from "@/components/layout/PageContainer";
import Badge from "@/components/ui/Badge";
import EmptyState from "@/components/ui/EmptyState";
import Loading from "@/components/ui/Loading";
import Select from "@/components/ui/Select";
import useBudget from "@/hooks/useBudget";
import { getApiErrorText } from "@/lib/errors";
import {
  compactCurrency,
  formatCurrency,
  formatPercent,
  formatSignedCurrency,
} from "@/lib/formatters";

function Ecart({ valeur }) {
  const numerique = Number(valeur);
  if (numerique === 0) {
    return (
      <span className="ecart ecart--nul">
        <Minus size={13} />
        stable
      </span>
    );
  }
  if (numerique > 0) {
    return (
      <span className="ecart ecart--hausse">
        <ArrowUpRight size={13} />
        {formatSignedCurrency(numerique)}
      </span>
    );
  }
  return (
    <span className="ecart ecart--baisse">
      <ArrowDownRight size={13} />
      {formatSignedCurrency(numerique)}
    </span>
  );
}

const COULEURS_PHASES = {
  engagement: "#1d4ed8",
  liquidation: "#0891b2",
  ordonnancement: "#d97706",
  paiement: "#059669",
};

function ExecutionChart({ donnees }) {
  if (!donnees || donnees.length === 0) return null;
  return (
    <div className="card card__padding chart-card">
      <h3 className="chart-card__title">Exécution mensuelle par phase</h3>
      <p className="chart-card__subtitle">
        Engagements, liquidations, ordonnancements, paiements et cumul des
        paiements
      </p>
      <div className="chart-card__body">
        <ResponsiveContainer width="100%" height={260}>
          <ComposedChart
            data={donnees}
            margin={{ top: 8, right: 8, left: 0, bottom: 0 }}
          >
            <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
            <XAxis
              dataKey="mois"
              tick={{ fontSize: 11 }}
              interval="preserveStartEnd"
            />
            <YAxis
              tickFormatter={compactCurrency}
              tick={{ fontSize: 11 }}
              width={58}
            />
            <Tooltip
              formatter={(valeur, nom) => [formatCurrency(valeur), nom]}
              labelFormatter={(mois) => `Période ${mois}`}
            />
            <Legend />
            {Object.entries(COULEURS_PHASES).map(([phase, couleur]) => (
              <Line
                key={phase}
                dataKey={phase}
                name={
                  phase === "paiement"
                    ? "Paiement (exécuté)"
                    : phase.charAt(0).toUpperCase() + phase.slice(1)
                }
                stroke={couleur}
                strokeWidth={phase === "paiement" ? 2.5 : 1.8}
                dot={false}
              />
            ))}
            <Line
              dataKey="cumul"
              name="Cumul payé"
              stroke="#6b7280"
              strokeWidth={2}
              strokeDasharray="6 4"
              dot={false}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

function RepartitionTypes({ items }) {
  if (!items || items.length === 0) return null;
  return (
    <div className="card card__padding chart-card">
      <h3 className="chart-card__title">Répartition par type de dépense</h3>
      <p className="chart-card__subtitle">
        Crédits ouverts versus exécution (paiements)
      </p>
      <div className="chart-card__body">
        <ResponsiveContainer width="100%" height={260}>
          <BarChart
            data={items}
            margin={{ top: 8, right: 8, left: 0, bottom: 0 }}
          >
            <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
            <XAxis dataKey="type" tick={{ fontSize: 11 }} />
            <YAxis
              tickFormatter={compactCurrency}
              tick={{ fontSize: 11 }}
              width={58}
            />
            <Tooltip
              formatter={(valeur, nom) => [formatCurrency(valeur), nom]}
            />
            <Legend />
            <Bar
              dataKey="credits"
              name="Crédits ouverts"
              fill="#1d4ed8"
              radius={[4, 4, 0, 0]}
            />
            <Bar
              dataKey="execute"
              name="Exécuté"
              fill="#059669"
              radius={[4, 4, 0, 0]}
            />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

const METRIQUES_COMPARAISON = [
  { cle: "credits", label: "Crédits ouverts" },
  { cle: "execute", label: "Exécuté (paiements)" },
  { cle: "disponible", label: "Disponible" },
  { cle: "solde", label: "Solde" },
];

export default function BudgetPage() {
  const {
    exercices,
    exercice,
    setExercice,
    synthese,
    loading,
    error,
    recharger,
  } = useBudget();

  const total = synthese?.total;
  const comparaison = synthese?.comparaison;
  const passe = comparaison && {
    credits: comparaison.credits_precedent,
    execute: comparaison.execute_precedent,
    disponible: comparaison.disponible_precedent,
    solde: comparaison.solde_precedent,
  };

  return (
    <PageContainer
      title="Budget RFM"
      subtitle="Crédits votés, exécution par phase et indicateurs dérivés"
      actions={
        exercices.length > 1 && (
          <Select
            label="Exercice"
            value={exercice ?? ""}
            onChange={(evenement) => setExercice(Number(evenement.target.value))}
            options={exercices.map((annee) => ({
              value: annee,
              label: `Exercice ${annee}`,
            }))}
            disabled={loading}
          />
        )
      }
    >
      {!synthese && loading && <Loading label="Calcul du budget…" />}

      {error && !synthese && (
        <div className="card card__padding">
          <EmptyState
            icon={Landmark}
            title="Impossible de charger le budget"
            description={getApiErrorText(error)}
            action={
              <button
                type="button"
                className="btn btn--primary btn--md"
                onClick={recharger}
              >
                <RefreshCcw size={15} />
                Réessayer
              </button>
            }
          />
        </div>
      )}

      {synthese && (
        <>
          <section>
            <div className="dash-grid">
              <StatCard
                icon={Landmark}
                label="LFI"
                value={formatCurrency(total.lfi)}
                sub="crédits initiaux votés"
              />
              <StatCard
                icon={Landmark}
                label="LFR"
                value={formatCurrency(total.lfr)}
                sub="loi de finances rectificative"
              />
              <StatCard
                icon={TrendingUp}
                label="Variation LFR / LFI"
                value={formatSignedCurrency(total.variation)}
                sub={
                  total.variation_pct != null
                    ? `${formatPercent(total.variation_pct)} du LFI`
                    : "pas de LFI voté"
                }
              />
              <StatCard
                icon={Coins}
                label="Crédits ouverts"
                value={formatCurrency(total.credits)}
                sub="LFR sinon LFI, par ligne"
                variant="primary"
              />
              <StatCard
                icon={Wallet}
                label="Engagement"
                value={formatCurrency(total.engagement)}
                sub="crédits engagés"
              />
              <StatCard
                icon={Wallet}
                label="Liquidation"
                value={formatCurrency(total.liquidation)}
                sub="services faits"
              />
              <StatCard
                icon={Wallet}
                label="Ordonnancement"
                value={formatCurrency(total.ordonnancement)}
                sub="mandats émis"
              />
              <StatCard
                icon={Wallet}
                label="Exécution (paiements)"
                value={formatCurrency(total.execute)}
                sub="montants payés"
                variant="success"
              />
              <StatCard
                icon={Wallet}
                label="Disponible"
                value={formatCurrency(total.disponible)}
                sub="crédits ouverts − engagements"
                variant="success"
              />
              <StatCard
                icon={Percent}
                label="Solde"
                value={formatSignedCurrency(total.solde)}
                sub={
                  total.solde < 0
                    ? "dépassement budgétaire"
                    : "crédits ouverts − paiements"
                }
                variant={total.solde < 0 ? "danger" : "default"}
              />
              <StatCard
                icon={Gauge}
                label="Taux d'exécution"
                value={formatPercent(total.taux_execution)}
                sub={`${formatNumberLigne(total)} ligne(s) budgétaire(s)`}
                variant={
                  total.taux_execution >= 0.8
                    ? "success"
                    : total.taux_execution >= 0.5
                      ? "warning"
                      : "danger"
                }
              />
            </div>
          </section>

          {comparaison && passe && (
            <section className="conv-section">
              <div className="conv-section__header">
                <span className="conv-section__icon">
                  <TrendingUp size={18} />
                </span>
                <div>
                  <h2 className="conv-section__title">
                    Comparaison avec l'exercice {comparaison.exercice_precedent}
                  </h2>
                  <p className="conv-section__subtitle">
                    Évolution des indicateurs budgétaires
                  </p>
                </div>
              </div>
              <div className="comparaison-grid">
                {METRIQUES_COMPARAISON.map(({ cle, label }) => (
                  <div key={cle} className="comparaison-card">
                    <span className="comparaison-card__label">{label}</span>
                    <span className="comparaison-card__valeur">
                      {formatCurrency(total[cle])}
                    </span>
                    <span className="comparaison-card__avant">
                      {formatCurrency(passe[cle])} en{" "}
                      {comparaison.exercice_precedent}
                    </span>
                    <Ecart valeur={comparaison[`ecart_${cle}`]} />
                    {cle === "credits" &&
                      comparaison.variation_pct_credits != null && (
                        <span className="comparaison-card__avant">
                          {formatPercent(comparaison.variation_pct_credits)} en
                          variation
                        </span>
                      )}
                  </div>
                ))}
              </div>
            </section>
          )}

          <section className="conv-section">
            <div className="conv-section__header">
              <span className="conv-section__icon">
                <CalendarRange size={18} />
              </span>
              <div>
                <h2 className="conv-section__title">Analyse de l'exécution</h2>
                <p className="conv-section__subtitle">
                  Série mensuelle des phases et répartition par type
                </p>
              </div>
            </div>
            <div className="dashboard-charts">
              <ExecutionChart donnees={synthese.serie_mensuelle} />
              <RepartitionTypes items={synthese.repartition_par_type} />
            </div>
          </section>

          <section className="conv-section">
            <div className="conv-section__header">
              <span className="conv-section__icon">
                <Landmark size={18} />
              </span>
              <div>
                <h2 className="conv-section__title">Crédits par ligne</h2>
                <p className="conv-section__subtitle">
                  LFI / LFR, variation et exécution ligne par ligne
                </p>
              </div>
            </div>

            <div className="card card__padding">
              {synthese.lignes.length === 0 && (
                <EmptyState
                  icon={Landmark}
                  title="Aucun crédit voté"
                  description="Aucune ligne budgétaire (LFI/LFR) pour cet exercice."
                />
              )}

              {synthese.lignes.length > 0 && (
                <div className="tableau">
                  <table className="tableau__table">
                    <thead>
                      <tr>
                        <th>Chapitre</th>
                        <th>Ligne</th>
                        <th>Libellé</th>
                        <th>Type</th>
                        <th>LFI</th>
                        <th>LFR</th>
                        <th>Variation</th>
                        <th>Crédits</th>
                        <th>Engagé</th>
                        <th>Liquidé</th>
                        <th>Ordonnancé</th>
                        <th>Exécuté</th>
                        <th>Disponible</th>
                        <th>Solde</th>
                        <th>Taux</th>
                      </tr>
                    </thead>
                    <tbody>
                      {synthese.lignes.map((ligne) => (
                        <tr key={ligne.ligne_budgetaire}>
                          <td className="tableau__code">{ligne.chapitre}</td>
                          <td className="tableau__code">{ligne.ligne_budgetaire}</td>
                          <td>
                            <span className="tableau__nom">{ligne.libelle}</span>
                          </td>
                          <td>
                            <Badge
                              variant={
                                ligne.type === "investissement"
                                  ? "info"
                                  : "neutral"
                              }
                            >
                              {ligne.type}
                            </Badge>
                          </td>
                          <td className="tableau__montant">
                            {formatCurrency(ligne.lfi)}
                          </td>
                          <td className="tableau__montant">
                            {formatCurrency(ligne.lfr)}
                          </td>
                          <td className="tableau__montant">
                            <span
                              className={
                                ligne.variation > 0
                                  ? "tableau__variation--hausse"
                                  : ligne.variation < 0
                                    ? "tableau__variation--baisse"
                                    : undefined
                              }
                            >
                              {formatSignedCurrency(ligne.variation)}
                            </span>
                            {ligne.variation_pct != null && (
                              <span className="tableau__sous-texte">
                                {formatPercent(ligne.variation_pct)}
                              </span>
                            )}
                          </td>
                          <td className="tableau__montant tableau__montant--fort">
                            {formatCurrency(ligne.credits)}
                          </td>
                          <td className="tableau__montant">
                            {formatCurrency(ligne.engagement)}
                          </td>
                          <td className="tableau__montant">
                            {formatCurrency(ligne.liquidation)}
                          </td>
                          <td className="tableau__montant">
                            {formatCurrency(ligne.ordonnancement)}
                          </td>
                          <td className="tableau__montant tableau__montant--execute">
                            {formatCurrency(ligne.execute)}
                          </td>
                          <td className="tableau__montant">
                            {formatCurrency(ligne.disponible)}
                          </td>
                          <td className="tableau__montant">
                            {formatCurrency(ligne.solde)}
                          </td>
                          <td>
                            <Badge
                              variant={
                                ligne.taux_execution >= 0.8
                                  ? "success"
                                  : ligne.taux_execution >= 0.5
                                    ? "warning"
                                    : "danger"
                              }
                            >
                              {formatPercent(ligne.taux_execution)}
                            </Badge>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </section>
        </>
      )}
    </PageContainer>
  );
}

function formatNumberLigne(total) {
  return total?.lignes_budgetaires ?? 0;
}