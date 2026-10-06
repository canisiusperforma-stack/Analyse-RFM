"use client";

import { useMemo } from "react";
import {
  Activity,
  FileText,
  LayoutDashboard,
  RefreshCcw,
  Users,
  Wallet,
} from "lucide-react";
import {
  Bar,
  CartesianGrid,
  Cell,
  ComposedChart,
  Legend,
  Line,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import DashboardSummary from "@/components/dashboard/DashboardSummary";
import StatCard from "@/components/dashboard/StatCard";
import PageContainer from "@/components/layout/PageContainer";
import EmptyState from "@/components/ui/EmptyState";
import Loading from "@/components/ui/Loading";
import Select from "@/components/ui/Select";
import { getApiErrorText } from "@/lib/errors";
import useDashboard from "@/hooks/useDashboard";
import { formatCurrency, formatNumber, formatPercent } from "@/lib/formatters";

const COULEURS = [
  "#1d4ed8",
  "#059669",
  "#d97706",
  "#dc2626",
  "#0284c7",
  "#7c3aed",
  "#0ea5e9",
  "#64748b",
];

const LABELS_STATUTS = {
  soumis: "Soumise",
  a_completer: "À compléter",
  en_cours: "En cours",
  valide: "Validée",
  refuse: "Refusée",
  paye: "Payée",
  annule: "Annulée",
  inconnu: "Inconnu",
};

const LABELS_SITUATION = {
  actif: "Actifs",
  pensionne: "Pensionnés",
  indeterminee: "Indéterminée",
};

const LABELS_TYPE = {
  fonctionnement: "Fonctionnement",
  investissement: "Investissement",
  inconnu: "Inconnu",
};

const LABELS_PRESTATION = {
  soins: "Soins",
  pharmacie: "Pharmacie",
  hospitalisation: "Hospitalisation",
  prothese: "Prothèses",
  autre: "Autre",
  inconnu: "Inconnu",
};

function libelle(item) {
  return (
    LABELS_STATUTS[item.statut] ||
    LABELS_SITUATION[item.situation] ||
    LABELS_TYPE[item.type] ||
    LABELS_PRESTATION[item.type_prestation] ||
    item.statut ||
    item.situation ||
    item.type ||
    item.type_prestation ||
    item.categorie ||
    item.name ||
    "Autre"
  );
}

function etiqueter(items) {
  return items.map((item) => ({
    ...item,
    name: libelle(item),
  }));
}

function compactAr(valeur) {
  const montant = Number(valeur);
  if (Number.isNaN(montant)) return "";
  if (Math.abs(montant) >= 1e9) return `${(montant / 1e9).toFixed(1)} Md`;
  if (Math.abs(montant) >= 1e6) return `${(montant / 1e6).toFixed(0)} M`;
  return `${Math.round(montant)} Ar`;
}

function PieRepartition({ titre, items }) {
  if (!items || items.length === 0) return null;
  return (
    <div className="card card__padding chart-card">
      <h3 className="chart-card__title">{titre}</h3>
      <div className="chart-card__pie">
        <ResponsiveContainer width="100%" height={220}>
          <PieChart>
            <Pie
              data={items}
              dataKey="total"
              nameKey="name"
              innerRadius={48}
              outerRadius={78}
              paddingAngle={2}
            >
              {items.map((item, index) => (
                <Cell key={item.name} fill={COULEURS[index % COULEURS.length]} />
              ))}
            </Pie>
            <Tooltip
              formatter={(valeur) => [formatNumber(valeur), "Dossiers"]}
            />
            <Legend verticalAlign="bottom" height={36} />
          </PieChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

function BudgetChart({ donnees }) {
  if (!donnees || donnees.length === 0) return null;
  return (
    <div className="card card__padding chart-card">
      <h3 className="chart-card__title">Exécution budgétaire mensuelle</h3>
      <div className="chart-card__body">
        <ResponsiveContainer width="100%" height={240}>
          <ComposedChart data={donnees} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
            <XAxis dataKey="mois" tick={{ fontSize: 11 }} interval="preserveStartEnd" />
            <YAxis
              yAxisId="montant"
              tickFormatter={compactAr}
              tick={{ fontSize: 11 }}
              width={54}
            />
            <Tooltip
              formatter={(valeur, nom) =>
                nom === "Cumul"
                  ? [formatCurrency(valeur), nom]
                  : [formatCurrency(valeur), "Montant mensuel"]
              }
            />
            <Legend />
            <Bar
              yAxisId="montant"
              dataKey="montant"
              name="Montant mensuel"
              fill="#1d4ed8"
              radius={[4, 4, 0, 0]}
            />
            <Line
              yAxisId="montant"
              dataKey="cumul"
              name="Cumul"
              stroke="#059669"
              strokeWidth={2}
              dot={false}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

function RemboursementsChart({ donnees }) {
  if (!donnees || donnees.length === 0) return null;
  return (
    <div className="card card__padding chart-card">
      <h3 className="chart-card__title">Demandes et remboursements mensuels</h3>
      <div className="chart-card__body">
        <ResponsiveContainer width="100%" height={240}>
          <ComposedChart data={donnees} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
            <XAxis dataKey="mois" tick={{ fontSize: 11 }} interval="preserveStartEnd" />
            <YAxis
              yAxisId="volume"
              tick={{ fontSize: 11 }}
              width={36}
              allowDecimals={false}
            />
            <YAxis
              yAxisId="montant"
              orientation="right"
              tickFormatter={compactAr}
              tick={{ fontSize: 11 }}
              width={54}
            />
            <Tooltip
              formatter={(valeur, nom) =>
                nom === "Remboursé"
                  ? [formatCurrency(valeur), nom]
                  : [formatNumber(valeur), nom]
              }
            />
            <Legend />
            <Bar
              yAxisId="volume"
              dataKey="demandes"
              name="Demandes"
              fill="#0284c7"
              radius={[4, 4, 0, 0]}
            />
            <Line
              yAxisId="montant"
              dataKey="montant_rembourse"
              name="Remboursé"
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

function RepartitionListe({ titre, items }) {
  if (!items || items.length === 0) return null;
  const total = items.reduce((somme, item) => somme + item.total, 0);

  return (
    <div className="card card__padding chart-card">
      <h3 className="chart-card__title">{titre}</h3>
      <ul className="repartition-list">
        {items.map((item) => {
          const nom = libelle(item);
          const part = total > 0 ? (item.total / total) * 100 : 0;
          return (
            <li key={nom} className="repartition-item">
              <div className="repartition-item__row">
                <span className="repartition-item__label">{nom}</span>
                <span className="repartition-item__value">
                  {formatNumber(item.total)}
                  <small>{part.toFixed(0)} %</small>
                </span>
              </div>
              <div className="repartition-item__track">
                <span
                  className="repartition-item__fill"
                  style={{ width: `${part}%` }}
                />
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function SectionTitre({ icone: Icon, titre, sousTitre }) {
  return (
    <div className="dash-section__header">
      <span className="dash-section__icon">
        <Icon size={18} />
      </span>
      <div>
        <h2 className="dash-section__title">{titre}</h2>
        {sousTitre && <p className="dash-section__subtitle">{sousTitre}</p>}
      </div>
    </div>
  );
}

export default function DashboardPage() {
  const {
    exercices,
    exercice,
    setExercice,
    synthese,
    loading,
    error,
    recharger,
  } = useDashboard();

  const population = synthese?.population ?? {};
  const budget = synthese?.budget ?? {};
  const remboursements = synthese?.remboursements ?? {};

  const situations = useMemo(
    () => etiqueter(population?.repartition_par_situation || []),
    [population]
  );
  const statuts = useMemo(
    () => etiqueter(remboursements?.repartition_par_statut || []),
    [remboursements]
  );
  const typesBudget = useMemo(
    () => etiqueter(budget?.repartition_par_type || []),
    [budget]
  );

  const analytique = Array.isArray(synthese?.analytique) ? synthese.analytique : [];
  const aucuneDonnee = analytique[0]?.cle === "aucune_donnee";

  return (
    <PageContainer
      title="Tableau de bord"
      subtitle="Synthèse des indicateurs clés calculés par le backend"
      actions={
        exercices.length > 1 && (
          <Select
            label="Exercice"
            value={exercice ?? ""}
            onChange={(evenement) =>
              setExercice(Number(evenement.target.value))
            }
            options={exercices.map((annee) => ({
              value: annee,
              label: `Exercice ${annee}`,
            }))}
            disabled={loading}
          />
        )
      }
    >
      {loading && !synthese && <Loading label="Calcul des indicateurs…" />}

      {error && !synthese && (
        <div className="card card__padding">
          <EmptyState
            icon={LayoutDashboard}
            title="Impossible de charger le tableau de bord"
            description={getApiErrorText(error)}
            action={
              <button
                type="button"
                className="btn btn--primary btn--md"
                onClick={() => recharger(exercice)}
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
                   <DashboardSummary evenements={analytique} />

          {aucuneDonnee ? (
            <div className="card card__padding">
              <EmptyState
                icon={LayoutDashboard}
                title="Aucune donnée à afficher"
                description="Le backend ne dispose d'aucun indicateur pour cet exercice. Amorcez la base (backend/scripts/seed.py) ou importez des données pour alimenter le tableau de bord."
              />
            </div>
          ) : (
            <>
              <section className="dash-section">
                <SectionTitre
                  icone={Users}
                  titre="Population"
                  sousTitre="Bénéficiaires recensés à fin d'exercice"
                />
                <div className="dash-grid">
                  <StatCard
                    icon={Users}
                    label="Bénéficiaires"
                     value={formatNumber(population?.total)}
                     sub="recensés à fin d'exercice"
                   />
                   <StatCard
                     icon={Activity}
                     label="Actifs"
                     value={formatNumber(population?.actifs)}
                     variant="info"
                   />
                   <StatCard
                     icon={Activity}
                     label="Pensionnés"
                     value={formatNumber(population?.pensionnes)}
                     variant="warning"
                   />
                   <StatCard
                     icon={FileText}
                     label="Bénéficiaires RFM"
                     value={formatNumber(population?.beneficiaires_rfm)}
                     sub="avec au moins une demande sur l'exercice"
                     variant="success"
                   />
                </div>
                <div className="dashboard-charts">
                  <PieRepartition titre="Répartition par situation" items={situations} />
                   <RepartitionListe
                     titre="Répartition par catégorie"
                     items={population?.repartition_par_categorie}
                   />
                </div>
              </section>

              <section className="dash-section">
                <SectionTitre
                  icone={Wallet}
                  titre="Budget"
                  sousTitre="Crédits votés et exécution par phase"
                />
                <div className="dash-grid dash-grid--md">
                  <StatCard
                    icon={Wallet}
                    label="LFI"
                     value={formatCurrency(budget?.lfi)}
                     sub="crédits votés"
                   />
                   <StatCard
                     icon={Wallet}
                     label="LFR"
                     value={formatCurrency(budget?.lfr)}
                     sub="crédits révisés"
                   />
                   <StatCard
                     icon={Wallet}
                     label="Crédits ouverts"
                     value={formatCurrency(budget?.credits_ouverts)}
                     variant="info"
                   />
                   <StatCard
                     icon={Activity}
                     label="Exécuté"
                     value={formatCurrency(budget?.execute)}
                     sub="paiements de l'exercice"
                     variant="success"
                   />
                   <StatCard
                     icon={Activity}
                     label="Engagé"
                     value={formatCurrency(budget?.engage)}
                     sub="engagements"
                   />
                   <StatCard
                     icon={Activity}
                     label="Liquidé"
                     value={formatCurrency(budget?.liquide)}
                     sub="liquidations"
                   />
                   <StatCard
                     icon={Activity}
                     label="Ordonnancé"
                     value={formatCurrency(budget?.ordonnance)}
                     sub="ordonnancements"
                   />
                   <StatCard
                     icon={Wallet}
                     label="Disponible"
                     value={formatCurrency(budget?.disponible)}
                     sub="crédits ouverts − engagements"
                     variant="success"
                   />
                   <StatCard
                     icon={Wallet}
                     label="Solde"
                     value={formatCurrency(budget?.solde)}
                     sub="crédits ouverts − exécuté"
                     variant={budget?.solde < 0 ? "danger" : "warning"}
                   />
                   <StatCard
                     icon={Activity}
                     label="Taux d'exécution"
                     value={formatPercent(budget?.taux_execution)}
                     sub="exécuté / crédits ouverts"
                     variant={
                       (budget?.taux_execution ?? 0) >= 0.8
                         ? "success"
                         : (budget?.taux_execution ?? 0) >= 0.6
                           ? "warning"
                           : "danger"
                     }
                   />
                </div>
                <div className="dashboard-charts">
                   <BudgetChart donnees={budget?.execution_mensuelle} />
                  <RepartitionListe
                    titre="Exécution par type de crédit"
                    items={typesBudget}
                  />
                </div>
              </section>

              <section className="dash-section">
                <SectionTitre
                  icone={FileText}
                  titre="Remboursements RFM"
                  sousTitre="Demandes et montants de l'exercice"
                />
                <div className="dash-grid dash-grid--md">
                  <StatCard
                    icon={FileText}
                    label="Demandes"
                     value={formatNumber(remboursements?.demandes)}
                     sub="déposées sur l'exercice"
                   />
                   <StatCard
                     icon={FileText}
                     label="Acceptées"
                     value={formatNumber(remboursements?.acceptees)}
                     variant="success"
                     sub="validées ou payées"
                   />
                   <StatCard
                     icon={FileText}
                     label="Rejetées"
                     value={formatNumber(remboursements?.rejetees)}
                     variant="danger"
                   />
                   <StatCard
                     icon={FileText}
                     label="En attente"
                     value={formatNumber(remboursements?.en_attente)}
                     variant="warning"
                     sub="soumises, à compléter ou en cours"
                   />
                   <StatCard
                     icon={Wallet}
                     label="Montant demandé"
                     value={formatCurrency(remboursements?.montant_demande)}
                   />
                   <StatCard
                     icon={Wallet}
                     label="Montant remboursé"
                     value={formatCurrency(remboursements?.montant_rembourse)}
                     variant="success"
                   />
                   <StatCard
                     icon={Activity}
                     label="Montant moyen demandé"
                     value={formatCurrency(remboursements?.montant_moyen_demande)}
                   />
                   <StatCard
                     icon={Activity}
                     label="Montant moyen remboursé"
                     value={formatCurrency(remboursements?.montant_moyen_rembourse)}
                     variant="info"
                   />
                   <StatCard
                     icon={Activity}
                     label="Taux d'acceptation"
                     value={formatPercent(remboursements?.taux_acceptation)}
                     variant={
                       (remboursements?.taux_acceptation ?? 0) >= 0.75
                         ? "success"
                         : (remboursements?.taux_acceptation ?? 0) >= 0.5
                           ? "warning"
                           : "danger"
                     }
                   />
                </div>
                <div className="dashboard-charts">
                   <RemboursementsChart donnees={remboursements?.serie_mensuelle} />
                   <PieRepartition titre="Répartition par statut" items={statuts} />
                 </div>
                 <div className="dashboard-charts dashboard-charts--prestations">
                   <RepartitionListe
                     titre="Répartition par type de prestation"
                     items={remboursements?.repartition_par_prestation}
                   />
                </div>
              </section>
            </>
          )}
        </>
      )}
    </PageContainer>
  );
}