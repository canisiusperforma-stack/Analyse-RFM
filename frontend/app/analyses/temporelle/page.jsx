"use client";

import {
  ArrowDownRight,
  ArrowUpRight,
  CalendarRange,
  Minus,
  Receipt,
  RefreshCcw,
  TrendingUp,
  Wallet,
} from "lucide-react";
import {
  Bar,
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
import useAnalyses from "@/hooks/useAnalyses";
import { getApiErrorText } from "@/lib/errors";
import {
  compactCurrency,
  formatCurrency,
  formatNumber,
  formatPercent,
  formatSignedCurrency,
} from "@/lib/formatters";

function Ecart({ valeur, decimale = false }) {
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
        {decimale
          ? formatNumber(numerique)
          : formatSignedCurrency(numerique)}
      </span>
    );
  }
  return (
    <span className="ecart ecart--baisse">
      <ArrowDownRight size={13} />
      {decimale ? formatNumber(numerique) : formatSignedCurrency(numerique)}
    </span>
  );
}

function ExecutionTaux({ taux }) {
  if (taux == null) return <span className="tableau__sous-texte">—</span>;
  return (
    <span className={`taux-ligne ${taux >= 0.8 ? "taux-ligne--bon" : taux >= 0.5 ? "taux-ligne--moyen" : "taux-ligne--faible"}`}>
      {formatPercent(taux)}
    </span>
  );
}

function EvolutionChart({ donnees }) {
  const mois = donnees.evolution;
  if (!mois || mois.length === 0) return null;
  return (
    <div className="card card__padding chart-card">
      <h3 className="chart-card__title">Évolution mensuelle</h3>
      <p className="chart-card__subtitle">
        Demandes déposées, montants demandés et montants remboursés par mois
      </p>
      <div className="chart-card__body">
        <ResponsiveContainer width="100%" height={260}>
          <ComposedChart
            data={mois}
            margin={{ top: 8, right: 8, left: 0, bottom: 0 }}
          >
            <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
            <XAxis dataKey="libelle" tick={{ fontSize: 11 }} />
            <YAxis
              yAxisId="volume"
              tick={{ fontSize: 11 }}
              width={36}
              allowDecimals={false}
            />
            <YAxis
              yAxisId="montant"
              orientation="right"
              tickFormatter={compactCurrency}
              tick={{ fontSize: 11 }}
              width={58}
            />
            <Tooltip
              formatter={(valeur, nom) =>
                nom === "Demandes"
                  ? [formatNumber(valeur), nom]
                  : [formatCurrency(valeur), nom]
              }
            />
            <Legend />
            <Bar
              yAxisId="volume"
              dataKey="demandes"
              name="Demandes"
              fill="#2563eb"
              radius={[4, 4, 0, 0]}
            />
            <Line
              yAxisId="montant"
              dataKey="montant_demande"
              name="Montant demandé"
              stroke="#0891b2"
              strokeWidth={2}
              strokeDasharray="5 4"
              dot={false}
            />
            <Line
              yAxisId="montant"
              dataKey="montant_paye"
              name="Montant remboursé"
              stroke="#d97706"
              strokeWidth={2}
              dot={false}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

function ComparaisonMensuelle({ donnees, exercicePrecedent }) {
  const courant = donnees.evolution;
  const precedent = donnees.evolution_precedente;
  if (!courant || courant.length === 0 || !precedent?.length) return null;
  const series = courant.map((item, index) => ({
    mois: item.libelle,
    [donnees.exercice]: item.demandes,
    [`Exercice ${exercicePrecedent}`]: precedent[index]?.demandes ?? 0,
  }));
  return (
    <div className="card card__padding chart-card">
      <h3 className="chart-card__title">Demandes comparées par mois</h3>
      <p className="chart-card__subtitle">
        Exercice {donnees.exercice} (en bleu) contre exercice{" "}
        {exercicePrecedent} (en gris)
      </p>
      <div className="chart-card__body">
        <ResponsiveContainer width="100%" height={260}>
          <ComposedChart
            data={series}
            margin={{ top: 8, right: 8, left: 0, bottom: 0 }}
          >
            <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
            <XAxis dataKey="mois" tick={{ fontSize: 11 }} />
            <YAxis tick={{ fontSize: 11 }} width={36} allowDecimals={false} />
            <Tooltip formatter={(valeur) => formatNumber(valeur)} />
            <Legend />
            <Bar
              dataKey={donnees.exercice}
              name={`Exercice ${donnees.exercice}`}
              fill="#2563eb"
              radius={[4, 4, 0, 0]}
            />
            <Bar
              dataKey={`Exercice ${exercicePrecedent}`}
              fill="#cbd5e1"
              radius={[4, 4, 0, 0]}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

function DetaillerMois({ donnees }) {
  const mois = donnees.evolution;
  if (!mois?.length) return null;
  return (
    <div className="card card__padding">
      <h3 className="chart-card__title">Détail mensuel</h3>
      <p className="chart-card__subtitle">
        Moyennes, taux d'exécution et variation par rapport au mois précédent
      </p>
      <div className="tableau tableau--scroll">
        <table className="tableau__table">
          <thead>
            <tr>
              <th>Mois</th>
              <th>Demandes</th>
              <th>Montant demandé</th>
              <th>Montant remboursé</th>
              <th>Payés</th>
              <th>Taux d'exécution</th>
              <th>Moyenne</th>
              <th>Moyenne remboursée</th>
            </tr>
          </thead>
          <tbody>
            {mois.map((moisItem, index) => (
              <tr key={moisItem.periode}>
                <td className="tableau__code">{moisItem.libelle}</td>
                <td>
                  <div className="tableau__empile">
                    <span>{formatNumber(moisItem.demandes)}</span>
                    {moisItem.variation_demandes != null && index > 0 && (
                      <Variation valeur={moisItem.variation_demandes} />
                    )}
                  </div>
                </td>
                <td>
                  <div className="tableau__empile">
                    <span className="tableau__montant">
                      {formatCurrency(moisItem.montant_demande)}
                    </span>
                    {moisItem.variation_montant != null && index > 0 && (
                      <Variation valeur={moisItem.variation_montant} />
                    )}
                  </div>
                </td>
                <td>
                  <div className="tableau__empile">
                    <span className="tableau__montant tableau__montant--execute">
                      {formatCurrency(moisItem.montant_paye)}
                    </span>
                    {moisItem.variation_paye != null && index > 0 && (
                      <Variation valeur={moisItem.variation_paye} />
                    )}
                  </div>
                </td>
                <td>{formatNumber(moisItem.payes)}</td>
                <td>
                  <ExecutionTaux taux={moisItem.taux_execution} />
                </td>
                <td className="tableau__montant">
                  {moisItem.demandes > 0
                    ? formatCurrency(moisItem.moyenne)
                    : "—"}
                </td>
                <td className="tableau__montant">
                  {moisItem.payes > 0
                    ? formatCurrency(moisItem.moyenne_paye)
                    : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Variation({ valeur }) {
  const numerique = Number(valeur);
  if (numerique > 0) {
    return (
      <span className="variation variation--hausse">
        <ArrowUpRight size={11} />
        {formatPercent(numerique)}
      </span>
    );
  }
  if (numerique < 0) {
    return (
      <span className="variation variation--baisse">
        <ArrowDownRight size={11} />
        {formatPercent(numerique)}
      </span>
    );
  }
  return (
    <span className="variation variation--nulle">
      <Minus size={11} />
      {formatPercent(numerique)}
    </span>
  );
}

const METRIQUES_COMPARAISON = [
  { cle: "demandes", label: "Demandes", decimale: true },
  { cle: "payes", label: "Payés", decimale: true },
  { cle: "montant_demande", label: "Montant demandé" },
  { cle: "montant_paye", label: "Montant remboursé" },
  { cle: "moyenne", label: "Montant moyen / dossier" },
];

export default function TemporellePage() {
  const {
    exercices,
    exercice,
    setExercice,
    donnees,
    loading,
    error,
    recharger,
  } = useAnalyses();

  const synthese = donnees?.synthese;
  const comparaison = donnees?.comparaison;
  const exercicePrecedent = comparaison?.exercice_precedent;

  return (
    <PageContainer
      title="Analyse temporelle"
      subtitle="Évolution mensuelle des demandes et des remboursements"
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
      {!donnees && loading && <Loading label="Calcul de l'analyse temporelle…" />}

      {error && !donnees && (
        <div className="card card__padding">
          <EmptyState
            icon={TrendingUp}
            title="Impossible de charger l'analyse temporelle"
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

      {donnees && (
        <>
          <section>
            <div className="dash-grid">
              <StatCard
                icon={Receipt}
                label="Demandes"
                value={formatNumber(synthese.demandes)}
                sub="dossiers déposés"
              />
              <StatCard
                icon={Receipt}
                label="Payés"
                value={formatNumber(synthese.payes)}
                sub="dossiers réglés"
                variant="info"
              />
              <StatCard
                icon={Wallet}
                label="Montant demandé"
                value={formatCurrency(synthese.montant_demande)}
                sub="somme des demandes"
              />
              <StatCard
                icon={Wallet}
                label="Montant remboursé"
                value={formatCurrency(synthese.montant_paye)}
                sub="dossiers payés"
                variant="success"
              />
              <StatCard
                icon={TrendingUp}
                label="Taux d'exécution"
                value={formatPercent(synthese.taux_execution)}
                sub="remboursé / demandé"
                variant="secondary"
              />
              <StatCard
                icon={CalendarRange}
                label="Moyenne mensuelle"
                value={formatNumber(synthese.moyenne_mensuelle.demandes)}
                sub={`${formatCurrency(synthese.moyenne_mensuelle.montant_demande)}/mois`}
              />
              <StatCard
                icon={Wallet}
                label="Montant moyen / dossier"
                value={formatCurrency(synthese.moyenne)}
                sub="par demande"
              />
              <StatCard
                icon={Wallet}
                label="Montant moyen remboursé"
                value={formatCurrency(synthese.moyenne_paye)}
                sub="par dossier payé"
                variant="success"
              />
            </div>
          </section>

          {comparaison && (
            <section className="conv-section">
              <div className="conv-section__header">
                <span className="conv-section__icon">
                  <ArrowUpRight size={18} />
                </span>
                <div>
                  <h2 className="conv-section__title">
                    Comparaison des périodes
                  </h2>
                  <p className="conv-section__subtitle">
                    Exercice {donnees.exercice} contre exercice{" "}
                    {exercicePrecedent}
                  </p>
                </div>
              </div>
              <div className="comparaison-grid">
                {METRIQUES_COMPARAISON.map(({ cle, label, decimale }) => (
                  <div key={cle} className="comparaison-card">
                    <span className="comparaison-card__label">{label}</span>
                    <span className="comparaison-card__valeur">
                      {decimale
                        ? formatNumber(comparaison[cle].courant)
                        : formatCurrency(comparaison[cle].courant)}
                    </span>
                    <span className="comparaison-card__avant">
                      {decimale
                        ? formatNumber(comparaison[cle].precedent)
                        : formatCurrency(comparaison[cle].precedent)}{" "}
                      en {exercicePrecedent}
                    </span>
                    <Ecart
                      valeur={comparaison[cle].ecart}
                      decimale={decimale}
                    />
                    {comparaison[cle].variation_pct != null && (
                      <span className="comparaison-card__avant">
                        {formatPercent(comparaison[cle].variation_pct)} en
                        variation
                      </span>
                    )}
                  </div>
                ))}
                <div className="comparaison-card">
                  <span className="comparaison-card__label">
                    Taux d'exécution
                  </span>
                  <span className="comparaison-card__valeur">
                    {formatPercent(comparaison.taux_execution.courant)}
                  </span>
                  <span className="comparaison-card__avant">
                    {formatPercent(comparaison.taux_execution.precedent)} en{" "}
                    {exercicePrecedent}
                  </span>
                  <Ecart
                    valeur={comparaison.taux_execution.ecart}
                    decimale
                  />
                </div>
              </div>
            </section>
          )}

          <section className="conv-section">
            <div className="conv-section__header">
              <span className="conv-section__icon">
                <TrendingUp size={18} />
              </span>
              <div>
                <h2 className="conv-section__title">Évolution dans le temps</h2>
                <p className="conv-section__subtitle">
                  Série mensuelle et comparaison entre exercices
                </p>
              </div>
            </div>
            <div className="dashboard-charts">
              <EvolutionChart donnees={donnees} />
              <ComparaisonMensuelle
                donnees={donnees}
                exercicePrecedent={exercicePrecedent}
              />
            </div>
          </section>

          <section className="conv-section">
            <div className="conv-section__header">
              <span className="conv-section__icon">
                <CalendarRange size={18} />
              </span>
              <div>
                <h2 className="conv-section__title">Tableau mensuel</h2>
                <p className="conv-section__subtitle">
                  Moyennes, taux d'exécution et variations mois après mois
                </p>
              </div>
            </div>
            <DetaillerMois donnees={donnees} />
          </section>
        </>
      )}
    </PageContainer>
  );
}