"use client";

import {
  BarChart3,
  Grid3x3,
  LineChart,
  RefreshCcw,
  Sigma,
  Users,
} from "lucide-react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
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
import useStatistiques from "@/hooks/useStatistiques";
import { getApiErrorText } from "@/lib/errors";
import {
  compactCurrency,
  formatCurrency,
  formatNumber,
  formatPercent,
} from "@/lib/formatters";

const VARIABLES_MONTANT = new Set([
  "montant_demande",
  "montant_accordee",
  "montant_paye",
]);

const LIGNES_DESCRIPTIVES = [
  ["montant_demande", "Montant demandé"],
  ["montant_accordee", "Montant accordé"],
  ["montant_paye", "Montant remboursé"],
  ["delai_jours", "Délai de traitement"],
  ["age_beneficiaire", "Âge du bénéficiaire"],
];

const COULEURS = ["#2563eb", "#0891b2", "#d97706", "#059669", "#7c3aed", "#dc2626"];

const INTENSITE_VARIANT = {
  forte: "success",
  moyenne: "warning",
  faible: "neutral",
};

function formaterValeur(variable, valeur) {
  if (valeur == null) return "—";
  if (VARIABLES_MONTANT.has(variable)) {
    return formatCurrency(valeur);
  }
  return formatNumber(valeur);
}

function couleurCorrelation(valeur) {
  if (valeur == null) return undefined;
  const intensite = Math.min(Math.abs(valeur), 1);
  const base = valeur >= 0 ? "37, 99, 235" : "220, 38, 38";
  return { backgroundColor: `rgba(${base}, ${0.08 + intensite * 0.32})` };
}

function TitreSection({ icone: Icone, titre, sousTitre }) {
  return (
    <div className="conv-section__header">
      <span className="conv-section__icon">
        <Icone size={18} />
      </span>
      <div>
        <h2 className="conv-section__title">{titre}</h2>
        <p className="conv-section__subtitle">{sousTitre}</p>
      </div>
    </div>
  );
}

function TableauDescriptives({ descriptives, variables }) {
  const colonnes = [
    ["nombre", "Effectif", "entier"],
    ["moyenne", "Moyenne", "valeur"],
    ["mediane", "Médiane", "valeur"],
    ["variance", "Variance", "nombre"],
    ["ecart_type", "Écart-type", "nombre"],
    ["minimum", "Minimum", "valeur"],
    ["maximum", "Maximum", "valeur"],
    ["somme", "Somme", "valeur"],
  ];
  return (
    <div className="card card__padding">
      <h3 className="chart-card__title">Statistiques descriptives</h3>
      <p className="chart-card__subtitle">
        Moyenne, médiane, variance et écart-type d'échantillon, quartiles,
        minimum et maximum — calculés avec NumPy
      </p>
      <div className="tableau tableau--scroll">
        <table className="tableau__table">
          <thead>
            <tr>
              <th>Variable</th>
              {colonnes.map(([, label]) => (
                <th key={label}>{label}</th>
              ))}
              <th>Q1</th>
              <th>Q2</th>
              <th>Q3</th>
            </tr>
          </thead>
          <tbody>
            {LIGNES_DESCRIPTIVES.map(([variable, label]) => {
              const stats = descriptives[variable];
              if (!stats) return null;
              return (
                <tr key={variable}>
                  <td className="tableau__nom">{label}</td>
                  {colonnes.map(([cle, , type]) => (
                    <td key={cle} className="tableau__montant">
                      {cle === "nombre"
                        ? formatNumber(stats.nombre)
                        : type === "nombre"
                          ? stats[cle] != null
                            ? formatNumber(stats[cle])
                            : "—"
                          : formaterValeur(variable, stats[cle])}
                    </td>
                  ))}
                  <td className="tableau__montant">
                    {formaterValeur(variable, stats.quartiles?.q1)}
                  </td>
                  <td className="tableau__montant">
                    {formaterValeur(variable, stats.quartiles?.mediane)}
                  </td>
                  <td className="tableau__montant">
                    {formaterValeur(variable, stats.quartiles?.q3)}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="chart-card__subtitle">{variables && Object.keys(variables).length > 0 ? `Variance et écart-type calculés sur l'échantillon (ddof = 1).` : ""}</p>
    </div>
  );
}

function Histogramme({ classes, titre }) {
  if (!classes || classes.length === 0) return null;
  const donnees = classes.map((classe) => ({
    intervalle: classe.intervalle,
    effectif: classe.effectif,
    pourcentage: classe.pourcentage,
  }));
  return (
    <div className="card card__padding chart-card">
      <h3 className="chart-card__title">{titre}</h3>
      <p className="chart-card__subtitle">Distribution en 5 classes égales</p>
      <div className="chart-card__body">
        <ResponsiveContainer width="100%" height={240}>
          <BarChart
            data={donnees}
            margin={{ top: 8, right: 8, left: 0, bottom: 0 }}
          >
            <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
            <XAxis dataKey="intervalle" tick={{ fontSize: 11 }} />
            <YAxis tick={{ fontSize: 11 }} width={36} allowDecimals={false} />
            <Tooltip
              formatter={(valeur, nom, item) =>
                nom === "effectif"
                  ? [
                      `${formatNumber(valeur)} (${formatPercent(item.payload.pourcentage)})`,
                      "Dossiers",
                    ]
                  : [valeur, nom]
              }
            />
            <Bar
              dataKey="effectif"
              name="effectif"
              fill="#2563eb"
              radius={[4, 4, 0, 0]}
            />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

function TableauPercentiles({ percentiles }) {
  const variables = Object.entries(percentiles || {});
  if (variables.length === 0) return null;
  const abscisses = Object.keys(variables[0][1]);
  return (
    <div className="card card__padding">
      <h3 className="chart-card__title">Percentiles</h3>
      <p className="chart-card__subtitle">
        Seuils (P1 à P99) des montants demandés et remboursés
      </p>
      <div className="tableau tableau--scroll">
        <table className="tableau__table">
          <thead>
            <tr>
              <th>Variable</th>
              {abscisses.map((abscisse) => (
                <th key={abscisse}>P{abscisse}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {variables.map(([variable, valeurs]) => (
              <tr key={variable}>
                <td className="tableau__nom">
                  {variable === "montant_demande"
                    ? "Montant demandé"
                    : "Montant remboursé"}
                </td>
                {abscisses.map((abscisse) => (
                  <td key={abscisse} className="tableau__montant">
                    {formaterValeur(variable, valeurs[abscisse])}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function MatriceCorrelations({ matrice, variables }) {
  const colonnes = Object.keys(matrice || {});
  if (colonnes.length < 2) return null;
  return (
    <div className="card card__padding">
      <h3 className="chart-card__title">Matrice de corrélation (Pearson)</h3>
      <p className="chart-card__subtitle">
        Coefficients entre les variables numériques — bleu positif, rouge négatif
      </p>
      <div className="tableau tableau--scroll">
        <table className="tableau__table">
          <thead>
            <tr>
              <th>Variable</th>
              {colonnes.map((colonne) => (
                <th key={colonne}>{variables?.[colonne] || colonne}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {colonnes.map((ligne) => (
              <tr key={ligne}>
                <td className="tableau__nom">
                  {variables?.[ligne] || ligne}
                </td>
                {colonnes.map((colonne) => {
                  const valeur = ligne === colonne ? 1 : matrice[ligne][colonne];
                  return (
                    <td
                      key={colonne}
                      className="tableau__montant"
                      style={couleurCorrelation(valeur)}
                    >
                      {valeur == null ? "—" : formatNumber(valeur.toFixed(2))}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function CorrelationsPertinentes({ paires, variables }) {
  if (!paires || paires.length === 0) return null;
  return (
    <div className="card card__padding">
      <h3 className="chart-card__title">Corrélations pertinentes</h3>
      <ul className="correlation-list">
        {paires.map((paire) => (
          <li
            key={`${paire.a}-${paire.b}`}
            className="correlation-item"
          >
            <div className="correlation-item__gauche">
              <span className="correlation-item__libelle">
                {variables?.[paire.a] || paire.a}
                <span className="correlation-item__fleche">↔</span>
                {variables?.[paire.b] || paire.b}
              </span>
              <div className="correlation-item__barre">
                <span
                  className={`correlation-item__remplissage correlation-item__remplissage--${paire.correlation >= 0 ? "positif" : "negatif"}`}
                  style={{ width: `${Math.min(Math.abs(paire.correlation), 1) * 100}%` }}
                />
              </div>
            </div>
            <div className="correlation-item__droite">
              <span className="correlation-item__valeur">
                {formatNumber(paire.correlation.toFixed(2))}
              </span>
              <Badge variant={INTENSITE_VARIANT[paire.intensite] || "neutral"}>
                {paire.intensite}
              </Badge>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}

function ComparaisonActifsPensionnes({ bloc }) {
  if (!bloc) return null;
  const { actifs, pensionnes, comparaison, effectifs_population } = bloc;
  const graphique = comparaison
    .filter((item) => item.type === "montant" && item.cle.startsWith("montant"))
    .map((item) => ({
      metrique: item.label,
      Actifs: item.actifs,
      Pensionnés: item.pensionnes,
    }));

  return (
    <div className="conv-section">
      <TitreSection
        icone={Users}
        titre="Comparaison actifs / pensionnés"
        sousTitre={`${formatNumber(effectifs_population?.actif ?? 0)} bénéficiaires actifs et ${formatNumber(effectifs_population?.pensionne ?? 0)} pensionnés enregistrés`}
      />
      <div className="comparaison-grid">
        {comparaison.map((item) => (
          <div key={item.cle} className="comparaison-card">
            <span className="comparaison-card__label">{item.label}</span>
            <div className="actif-pensionne">
              <div>
                <span className="actif-pensionne__tag">Actifs</span>
                <span className="actif-pensionne__valeur">
                  {item.type === "montant"
                    ? formatCurrency(item.actifs)
                    : item.type === "taux"
                      ? formatPercent(item.actifs)
                      : formatNumber(item.actifs)}
                </span>
              </div>
              <div>
                <span className="actif-pensionne__tag">Pensionnés</span>
                <span className="actif-pensionne__valeur">
                  {item.type === "montant"
                    ? formatCurrency(item.pensionnes)
                    : item.type === "taux"
                      ? formatPercent(item.pensionnes)
                      : formatNumber(item.pensionnes)}
                </span>
              </div>
            </div>
            <span className="comparaison-card__avant">
              Écart :{" "}
              {item.type === "montant"
                ? formatCurrency(item.ecart)
                : item.type === "taux"
                  ? formatPercent(item.ecart)
                  : formatNumber(item.ecart)}
              {item.ratio != null && ` · ratio ${formatNumber(item.ratio.toFixed(2))}`}
            </span>
          </div>
        ))}
      </div>

      {graphique.length > 0 && (
        <div className="dashboard-charts" style={{ marginTop: 16 }}>
          <div className="card card__padding chart-card">
            <h3 className="chart-card__title">Montants par situation</h3>
            <p className="chart-card__subtitle">
              Montants demandés et remboursés selon le statut
            </p>
            <div className="chart-card__body">
              <ResponsiveContainer width="100%" height={240}>
                <BarChart
                  data={graphique}
                  margin={{ top: 8, right: 8, left: 0, bottom: 0 }}
                >
                  <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                  <XAxis dataKey="metrique" tick={{ fontSize: 11 }} />
                  <YAxis
                    tickFormatter={compactCurrency}
                    tick={{ fontSize: 11 }}
                    width={58}
                  />
                  <Tooltip formatter={(valeur) => formatCurrency(valeur)} />
                  <Legend />
                  <Bar dataKey="Actifs" fill="#2563eb" radius={[4, 4, 0, 0]} />
                  <Bar
                    dataKey="Pensionnés"
                    fill="#d97706"
                    radius={[4, 4, 0, 0]}
                  />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default function StatistiquesPage() {
  const {
    exercices,
    exercice,
    setExercice,
    donnees,
    loading,
    error,
    recharger,
  } = useStatistiques();

  const descriptives = donnees?.descriptives;
  const demande = descriptives?.montant_demande;
  const paye = descriptives?.montant_paye;
  const delai = descriptives?.delai_jours;
  const age = descriptives?.age_beneficiaire;

  return (
    <PageContainer
      title="Statistiques"
      subtitle="Module Data Science — Pandas & NumPy"
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
      {!donnees && loading && <Loading label="Calcul des statistiques…" />}

      {error && !donnees && (
        <div className="card card__padding">
          <EmptyState
            icon={Sigma}
            title="Impossible de charger les statistiques"
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
                icon={Sigma}
                label="Dossiers analysés"
                value={formatNumber(donnees.nombre_documents)}
                sub={donnees.methode}
              />
              <StatCard
                icon={BarChart3}
                label="Montant moyen"
                value={formatCurrency(demande?.moyenne)}
                sub={`médiane : ${formatCurrency(demande?.mediane)}`}
              />
              <StatCard
                icon={Sigma}
                label="Écart-type"
                value={formatNumber(demande?.ecart_type)}
                sub={`variance : ${formatNumber(demande?.variance)}`}
                variant="secondary"
              />
              <StatCard
                icon={BarChart3}
                label="Montant remboursé"
                value={formatCurrency(paye?.somme)}
                sub={`moyenne : ${formatCurrency(paye?.moyenne)}`}
                variant="success"
              />
              <StatCard
                icon={LineChart}
                label="Délai moyen"
                value={`${formatNumber(delai?.moyenne)} j`}
                sub={`médiane : ${formatNumber(delai?.mediane)} j`}
                variant="warning"
              />
              <StatCard
                icon={Users}
                label="Âge moyen"
                value={`${formatNumber(age?.moyenne)} ans`}
                sub={`min ${formatNumber(age?.minimum)} – max ${formatNumber(age?.maximum)}`}
                variant="info"
              />
            </div>
          </section>

          <section className="conv-section">
            <TitreSection
              icone={Sigma}
              titre="Statistiques descriptives"
              sousTitre="Tendances centrales, dispersion et quartiles"
            />
            <TableauDescriptives
              descriptives={descriptives}
              variables={donnees.variables}
            />
          </section>

          <section className="conv-section">
            <TitreSection
              icone={BarChart3}
              titre="Distributions"
              sousTitre="Histogrammes et percentiles des montants"
            />
            <div className="dashboard-charts">
              <Histogramme
                classes={donnees.distributions?.montant_demande}
                titre="Distribution des montants demandés"
              />
              <Histogramme
                classes={donnees.distributions?.montant_paye}
                titre="Distribution des montants remboursés"
              />
            </div>
            <div style={{ marginTop: 16 }}>
              <TableauPercentiles percentiles={donnees.percentiles} />
            </div>
          </section>

          <section className="conv-section">
            <TitreSection
              icone={Grid3x3}
              titre="Corrélations"
              sousTitre="Relations entre montants, délais et âge"
            />
            <div className="dashboard-charts">
              <MatriceCorrelations
                matrice={donnees.correlations?.matrice}
                variables={donnees.variables}
              />
              <CorrelationsPertinentes
                paires={donnees.correlations?.pertinentes}
                variables={donnees.variables}
              />
            </div>
          </section>

          <ComparaisonActifsPensionnes bloc={donnees.actifs_pensionnes} />
        </>
      )}
    </PageContainer>
  );
}