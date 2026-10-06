"use client";

import { useEffect, useState } from "react";
import {
  AlertTriangle,
  BarChart3,
  BookOpen,
  Coins,
  Download,
  FileDown,
  TrendingUp,
  Users,
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

import RequirePermission from "@/components/auth/RequirePermission";
import StatCard from "@/components/dashboard/StatCard";
import PageContainer from "@/components/layout/PageContainer";
import Badge from "@/components/ui/Badge";
import Button from "@/components/ui/Button";
import EmptyState from "@/components/ui/EmptyState";
import Loading from "@/components/ui/Loading";
import Select from "@/components/ui/Select";
import { getApiErrorText } from "@/lib/errors";
import {
  formatCurrency,
  formatDate,
  formatNumber,
  formatPercent,
} from "@/lib/formatters";
import { recupererAnomalies } from "@/services/anomalieService";
import {
  exporterExcel,
  recupererExercices,
  recupererRapport,
} from "@/services/rapportService";

const MOIS = [
  "Janvier",
  "Février",
  "Mars",
  "Avril",
  "Mai",
  "Juin",
  "Juillet",
  "Août",
  "Septembre",
  "Octobre",
  "Novembre",
  "Décembre",
];

const LABELS_STATUT = {
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

const LABELS_CATEGORIE = {
  militaire: "Militaire",
  civil: "Civil",
  autre: "Autre",
  inconnue: "Inconnue",
};

const LABELS_TYPE_BUDGET = {
  fonctionnement: "Fonctionnement",
  investissement: "Investissement",
  inconnu: "Inconnu",
};

const LABELS_NIVEAU = {
  observation_atypique: { label: "Observation atypique", variant: "info" },
  anomalie_potentielle: { label: "Anomalie potentielle", variant: "warning" },
  valeur_a_verifier: { label: "Valeur à vérifier", variant: "danger" },
};

function nomMois(mois) {
  return MOIS[(Number(mois) - 1) % 12] ?? mois;
}

function libelle(labels, cle) {
  return labels[cle] ?? cle ?? "—";
}

function etiqueter(items, labels) {
  return (items || []).map((item) => {
    const cle = item.situation ?? item.categorie ?? item.statut ?? item.type_prestation ?? item.type;
    return { ...item, name: libelle(labels, cle) };
  });
}

function compactAr(valeur) {
  const montant = Number(valeur);
  if (Number.isNaN(montant)) return "";
  if (Math.abs(montant) >= 1e9) return `${(montant / 1e9).toFixed(1)} Md`;
  if (Math.abs(montant) >= 1e6) return `${(montant / 1e6).toFixed(0)} M`;
  return `${Math.round(montant)} Ar`;
}

const onglets = [
  { id: "contexte", label: "Contexte", icon: BookOpen },
  { id: "beneficiaires", label: "Bénéficiaires", icon: Users },
  { id: "budget", label: "Budget", icon: Coins },
  { id: "execution", label: "Exécution", icon: TrendingUp },
  { id: "remboursements", label: "Remboursements", icon: Coins },
  { id: "graphiques", label: "Graphiques", icon: BarChart3 },
  { id: "anomalies", label: "Observations atypiques", icon: AlertTriangle },
  { id: "resume", label: "Résumé analytique", icon: BarChart3 },
];

function ChampTableau({ titre, colonnes = [], lignes = [] }) {
  if (lignes.length === 0) return null;
  return (
    <div style={{ marginBottom: "2rem" }}>
      <h4 style={{ marginBottom: "0.75rem", color: "#1f2937" }}>{titre}</h4>
      <div style={{ overflowX: "auto" }}>
        <table
          style={{
            width: "100%",
            borderCollapse: "collapse",
            fontSize: "0.875rem",
          }}
        >
          <thead>
            <tr style={{ background: "#f3f4f6" }}>
              {colonnes.map((c, i) => (
                <th
                  key={i}
                  style={{
                    padding: "0.75rem",
                    textAlign: "left",
                    border: "1px solid #e5e7eb",
                    fontWeight: "600",
                    color: "#374151",
                    whiteSpace: "nowrap",
                  }}
                >
                  {c}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {lignes.map((ligne, idx) => (
              <tr key={idx} style={{ background: idx % 2 ? "#fff" : "#fafafa" }}>
                {ligne.map((cell, j) => (
                  <td
                    key={j}
                    style={{
                      padding: "0.625rem 0.75rem",
                      border: "1px solid #e5e7eb",
                      color: "#374151",
                      verticalAlign: "top",
                    }}
                  >
                    {cell}
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

function ContexteSection({ rapport }) {
  const population = rapport.population ?? {};
  const totalBudget = rapport.budget?.total ?? {};
  const remboursements = rapport.remboursements ?? {};

  return (
    <div>
      <div className="stat-grid" style={{ marginBottom: "1.5rem" }}>
        <StatCard
          icon={Users}
          label="Population recensée"
          value={formatNumber(population.total)}
          sub={`${formatNumber(population.beneficiaires_rfm)} ayant une demande RFM`}
        />
        <StatCard
          icon={Coins}
          label="Budget initial (LFI)"
          value={formatCurrency(totalBudget.lfi)}
          sub={`Budget ajusté : ${formatCurrency(totalBudget.lfr)}`}
        />
        <StatCard
          icon={TrendingUp}
          label="Paiements exécutés"
          value={formatCurrency(totalBudget.execute)}
          sub={`Taux d'exécution : ${formatPercent(totalBudget.taux_execution)}`}
        />
        <StatCard
          icon={Download}
          label="Demandes déposées"
          value={formatNumber(remboursements.demandes)}
          sub={`${formatNumber(remboursements.acceptees)} acceptées`}
        />
      </div>
      <p className="text-muted" style={{ marginTop: 0 }}>
        Rapport calculé automatiquement à partir des données métier (budgets,
        exécutions, remboursements, bénéficiaires) pour l'exercice{" "}
        <strong>{rapport.exercice}</strong>. Aucun chiffre n'est figé.
      </p>
    </div>
  );
}

function BeneficiairesSection({ rapport }) {
  const population = rapport.population ?? {};
  return (
    <div>
      <ChampTableau
        titre="Répartition par situation"
        colonnes={["Situation", "Effectif"]}
        lignes={(population.repartition_par_situation || []).map((item) => [
          libelle(LABELS_SITUATION, item.situation),
          formatNumber(item.total),
        ])}
      />
      <ChampTableau
        titre="Répartition par catégorie"
        colonnes={["Catégorie", "Effectif"]}
        lignes={(population.repartition_par_categorie || []).map((item) => [
          libelle(LABELS_CATEGORIE, item.categorie),
          formatNumber(item.total),
        ])}
      />
    </div>
  );
}

function BudgetSection({ rapport }) {
  const bougie = rapport.budget ?? {};
  const total = bougie.total ?? {};
  return (
    <div>
      <div className="stat-grid" style={{ marginBottom: "1.5rem" }}>
        <StatCard icon={Coins} label="LFI" value={formatCurrency(total.lfi)} />
        <StatCard icon={Coins} label="LFR" value={formatCurrency(total.lfr)} />
        <StatCard icon={Coins} label="Crédits ouverts" value={formatCurrency(total.credits)} />
        <StatCard
          icon={TrendingUp}
          label="Exécuté (paiements)"
          value={formatCurrency(total.execute)}
          sub={`Taux : ${formatPercent(total.taux_execution)}`}
        />
        <StatCard
          icon={Coins}
          label="Disponible"
          value={formatCurrency(total.disponible)}
        />
      </div>

      <ChampTableau
        titre="Lignes budgétaires et exécution par phase"
        colonnes={[
          "Chapitre",
          "Ligne",
          "Libellé",
          "Type",
          "LFI",
          "LFR",
          "Crédits",
          "Engagé",
          "Liquidé",
          "Ordonnancé",
          "Payé",
          "Disponible",
          "Taux exéc.",
        ]}
        lignes={[
          ...(bougie.lignes || []).map((ligne) => [
            ligne.chapitre ?? "",
            ligne.ligne_budgetaire ?? "",
            ligne.libelle ?? "",
            libelle(LABELS_TYPE_BUDGET, ligne.type),
            formatCurrency(ligne.lfi),
            formatCurrency(ligne.lfr),
            formatCurrency(ligne.credits),
            formatCurrency(ligne.engagement),
            formatCurrency(ligne.liquidation),
            formatCurrency(ligne.ordonnancement),
            formatCurrency(ligne.execute),
            formatCurrency(ligne.disponible),
            formatPercent(ligne.taux_execution),
          ]),
          [
            <strong key="total">Total</strong>,
            "",
            "",
            "",
            <strong key="lfid">{formatCurrency(total.lfi)}</strong>,
            <strong key="lfrd">{formatCurrency(total.lfr)}</strong>,
            <strong key="cr">{formatCurrency(total.credits)}</strong>,
            <strong key="en">{formatCurrency(total.engagement)}</strong>,
            <strong key="li">{formatCurrency(total.liquidation)}</strong>,
            <strong key="or">{formatCurrency(total.ordonnancement)}</strong>,
            <strong key="ex">{formatCurrency(total.execute)}</strong>,
            <strong key="di">{formatCurrency(total.disponible)}</strong>,
            <strong key="tx">{formatPercent(total.taux_execution)}</strong>,
          ],
        ]}
      />

      <ChampTableau
        titre="Ventilation par type"
        colonnes={["Type", "Crédits", "Exécuté", "Taux exéc.", "Lignes"]}
        lignes={(bougie.repartition_par_type || []).map((item) => [
          libelle(LABELS_TYPE_BUDGET, item.type),
          formatCurrency(item.credits),
          formatCurrency(item.execute),
          formatPercent(item.taux_execution),
          formatNumber(item.lignes),
        ])}
      />
    </div>
  );
}

function ExecutionSection({ rapport }) {
  const serie = rapport.budget?.serie_mensuelle || [];
  const total = rapport.budget?.total ?? {};
  const ligneTotale = [
    <strong key="m">Total</strong>,
    <strong key="e">{formatCurrency(total.engagement)}</strong>,
    <strong key="l">{formatCurrency(total.liquidation)}</strong>,
    <strong key="o">{formatCurrency(total.ordonnancement)}</strong>,
    <strong key="p">{formatCurrency(total.execute)}</strong>,
    "",
  ];
  return (
    <ChampTableau
      titre="Paiements exécutés par mois"
      colonnes={["Mois", "Engagement", "Liquidation", "Ordonnancement", "Paiement", "Cumul"]}
      lignes={[
        ...serie.map((item) => [
          nomMois(item.mois),
          formatCurrency(item.engagement),
          formatCurrency(item.liquidation),
          formatCurrency(item.ordonnancement),
          formatCurrency(item.paiement),
          formatCurrency(item.cumul),
        ]),
        ligneTotale,
      ]}
    />
  );
}

function RemboursementsSection({ rapport }) {
  const remboursements = rapport.remboursements ?? {};
  return (
    <div>
      <div className="stat-grid" style={{ marginBottom: "1.5rem" }}>
        <StatCard
          icon={Download}
          label="Demandes"
          value={formatNumber(remboursements.demandes)}
          sub={`${formatNumber(remboursements.acceptees)} acceptées`}
        />
        <StatCard
          icon={AlertTriangle}
          label="Refusées"
          value={formatNumber(remboursements.rejetees)}
        />
        <StatCard
          icon={Coins}
          label="Montant demandé"
          value={formatCurrency(remboursements.montant_demande)}
        />
        <StatCard
          icon={TrendingUp}
          label="Montant remboursé"
          value={formatCurrency(remboursements.montant_rembourse)}
          sub={`Taux d'acceptation : ${formatPercent(remboursements.taux_acceptation)}`}
        />
      </div>

      <ChampTableau
        titre="Répartition par statut"
        colonnes={["Statut", "Effectif"]}
        lignes={(remboursements.repartition_par_statut || []).map((item) => [
          libelle(LABELS_STATUT, item.statut),
          formatNumber(item.total),
        ])}
      />

      <ChampTableau
        titre="Répartition par type de prestation"
        colonnes={["Prestation", "Effectif"]}
        lignes={(remboursements.repartition_par_prestation || []).map((item) => [
          item.type_prestation ?? "—",
          formatNumber(item.total),
        ])}
      />

      <ChampTableau
        titre="Série mensuelle"
        colonnes={["Mois", "Demandes", "Montant demandé", "Remboursés", "Montant remboursé"]}
        lignes={(remboursements.serie_mensuelle || []).map((item) => [
          nomMois(item.mois),
          formatNumber(item.demandes),
          formatCurrency(item.montant_demande),
          formatNumber(item.rembourses),
          formatCurrency(item.montant_rembourse),
        ])}
      />
    </div>
  );
}

function GraphiquesSection({ rapport }) {
  const serieBudget = (rapport.budget?.serie_mensuelle || []).map((item) => ({
    mois: nomMois(item.mois),
    montant: item.paiement,
    cumul: item.cumul,
  }));
  const serieRemb = (rapport.remboursements?.serie_mensuelle || []).map(
    (item) => ({
      mois: nomMois(item.mois),
      demandes: item.demandes,
      montant_rembourse: item.montant_rembourse,
    })
  );

  return (
    <div className="dashboard-charts">
      <div className="card card__padding chart-card">
        <h3 className="chart-card__title">Exécution budgétaire mensuelle</h3>
        <ResponsiveContainer width="100%" height={260}>
          <ComposedChart data={serieBudget} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
            <XAxis dataKey="mois" tick={{ fontSize: 11 }} interval="preserveStartEnd" />
            <YAxis tickFormatter={compactAr} tick={{ fontSize: 11 }} width={56} />
            <Tooltip
              formatter={(valeur, nom) =>
                nom === "Cumul"
                  ? [formatCurrency(valeur), nom]
                  : [formatCurrency(valeur), "Montant mensuel"]
              }
            />
            <Legend />
            <Bar dataKey="montant" name="Montant mensuel" fill="#1d4ed8" radius={[4, 4, 0, 0]} />
            <Line dataKey="cumul" name="Cumul" stroke="#059669" strokeWidth={2} dot={false} />
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      <div className="card card__padding chart-card">
        <h3 className="chart-card__title">Demandes et remboursements mensuels</h3>
        <ResponsiveContainer width="100%" height={260}>
          <ComposedChart data={serieRemb} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
            <XAxis dataKey="mois" tick={{ fontSize: 11 }} interval="preserveStartEnd" />
            <YAxis yAxisId="volume" tick={{ fontSize: 11 }} width={36} allowDecimals={false} />
            <YAxis yAxisId="montant" orientation="right" tickFormatter={compactAr} tick={{ fontSize: 11 }} width={56} />
            <Tooltip
              formatter={(valeur, nom) =>
                nom === "Remboursé"
                  ? [formatCurrency(valeur), nom]
                  : [formatNumber(valeur), nom]
              }
            />
            <Legend />
            <Bar yAxisId="volume" dataKey="demandes" name="Demandes" fill="#0284c7" radius={[4, 4, 0, 0]} />
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

function AnomaliesSection({ exercice, actif }) {
  const [donnees, setDonnees] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!actif || exercice == null) return;
    let annule = false;
    setLoading(true);
    setError(null);
    (async () => {
      try {
        const resultat = await recupererAnomalies({ exercice, limite: 10 });
        if (!annule) setDonnees(resultat);
      } catch (e) {
        if (!annule) setError(e);
      } finally {
        if (!annule) setLoading(false);
      }
    })();
    return () => {
      annule = true;
    };
  }, [actif, exercice]);

  if (loading && !donnees) return <Loading label="Analyse des observations atypiques…" />;
  if (error && !donnees) {
    return (
      <div className="card card__padding">
        <EmptyState
          icon={AlertTriangle}
          title="Observations atypiques indisponibles"
          description={getApiErrorText(error)}
        />
      </div>
    );
  }
  if (!donnees) return null;

  const comptes = donnees.comptes ?? {};
  const items = donnees.items ?? [];

  return (
    <div>
      <div className="stat-grid" style={{ marginBottom: "1.5rem" }}>
        <StatCard
          icon={AlertTriangle}
          label="Alertes détectées"
          value={formatNumber(donnees.total)}
        />
        {Object.entries(LABELS_NIVEAU).map(([cle, infos]) => (
          <StatCard
            key={cle}
            icon={BarChart3}
            label={infos.label}
            value={formatNumber(comptes.par_niveau?.[cle])}
          />
        ))}
      </div>

      <ChampTableau
        titre="Dernières alertes"
        colonnes={["Niveau", "Dossier", "Bénéficiaire", "Variable", "Valeur", "Détectée le"]}
        lignes={items.map((item) => [
          <Badge key="b" variant={LABELS_NIVEAU[item.niveau]?.variant ?? "neutral"}>
            {LABELS_NIVEAU[item.niveau]?.label ?? item.niveau}
          </Badge>,
          item.numero_dossier ?? "—",
          item.beneficiaire?.nom
            ? `${item.beneficiaire.nom} ${item.beneficiaire.prenom ?? ""}`.trim()
            : "—",
          item.libelle_variable ?? "—",
          formatNumber(item.valeur),
          formatDate(item.detecte_le),
        ])}
      />
      <p className="text-muted" style={{ marginTop: 0 }}>
        Détection automatique par la plateforme (méthodes IQR, z-score,
        isolation forest, LOF) sur les remboursements de l'exercice.
      </p>
    </div>
  );
}

function ResumeAnalytiqueSection({ rapport }) {
  const evenements = Array.isArray(rapport.analytique) ? rapport.analytique : [];
  if (evenements.length === 0) {
    return (
      <EmptyState
        icon={BarChart3}
        title="Aucun constat à ce stade"
        description="Les constats automatiques apparaîtront ici après consolidation des données de l'exercice."
      />
    );
  }
  return (
    <ChampTableau
      titre="Constats automatiques"
      colonnes={["Niveau", "Message"]}
      lignes={evenements.map((item, index) => [
        <Badge key={index} variant={item.niveau === "alerte" ? "danger" : item.niveau === "avertissement" ? "warning" : "info"}>
          {item.niveau ?? "information"}
        </Badge>,
        item.message ?? "",
      ])}
    />
  );
}

function RapportsContenu() {
  const [exercices, setExercices] = useState([]);
  const [exercice, setExercice] = useState(null);
  const [rapport, setRapport] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [exportActif, setExportActif] = useState(false);
  const [erreurExport, setErreurExport] = useState(null);
  const [ongletActif, setOngletActif] = useState("contexte");

  useEffect(() => {
    let annule = false;
    (async () => {
      try {
        const disponibles = await recupererExercices();
        if (annule) return;
        setExercices(disponibles);
        setExercice(disponibles[0] ?? null);
      } catch (e) {
        if (!annule) setError(e);
      }
    })();
    return () => {
      annule = true;
    };
  }, []);

  useEffect(() => {
    if (exercice == null) return;
    let annule = false;
    setLoading(true);
    setError(null);
    (async () => {
      try {
        const donnees = await recupererRapport(exercice);
        if (!annule) setRapport(donnees);
      } catch (e) {
        if (!annule) setError(e);
      } finally {
        if (!annule) setLoading(false);
      }
    })();
    return () => {
      annule = true;
    };
  }, [exercice]);

  const exporter = async () => {
    if (!rapport) return;
    setExportActif(true);
    setErreurExport(null);
    try {
      await exporterExcel(rapport.exercice);
    } catch (e) {
      setErreurExport(getApiErrorText(e));
    } finally {
      setExportActif(false);
    }
  };

  if (loading && !rapport) {
    return <Loading label="Préparation du rapport…" />;
  }

  if (error && !rapport) {
    return (
      <PageContainer title="Rapport d'analyse RFM">
        <div className="card card__padding">
          <EmptyState
            icon={BookOpen}
            title="Impossible de charger le rapport"
            description={getApiErrorText(error)}
          />
        </div>
      </PageContainer>
    );
  }

  if (!rapport) {
    return (
      <PageContainer title="Rapport d'analyse RFM">
        <div className="card card__padding">
          <EmptyState
            icon={BookOpen}
            title="Exercice en attente"
            description="Importez un exercice (page Imports) ou réinitialisez les données de démonstration pour générer un rapport."
          />
        </div>
      </PageContainer>
    );
  }

  return (
    <PageContainer
      title={`Rapport d'analyse RFM ${rapport.exercice}`}
      subtitle={`Période d'analyse : 01 janvier ${rapport.exercice} – 31 décembre ${rapport.exercice}`}
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
      <div className="rapports-page">
        <div className="card card--padding">
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "flex-start",
              flexWrap: "wrap",
              gap: "1rem",
              marginBottom: "1.5rem",
            }}
          >
            <div>
              <h2 style={{ marginBottom: "0.5rem", color: "#1f2937" }}>
                Rapport d'analyse RFM {rapport.exercice}
              </h2>
              <p className="text-muted" style={{ margin: 0 }}>
                Objet : Analyse du portefeuille RFM (Récence – Fréquence – Montant)
              </p>
              <p className="text-muted" style={{ margin: "0.25rem 0 0 0" }}>
                Date de réalisation : {formatDate(rapport.calcule_le)}
              </p>
              {erreurExport && (
                <p className="alert alert--error" role="alert" style={{ margin: "0.5rem 0 0 0" }}>
                  {erreurExport}
                </p>
              )}
            </div>
            <RequirePermission permission="rapports:exporter">
              <Button onClick={exporter} loading={exportActif}>
                <FileDown size={18} />
                Exporter Excel structuré
              </Button>
            </RequirePermission>
          </div>

          <div
            className="tabs"
            style={{
              display: "flex",
              flexWrap: "wrap",
              gap: "0.5rem",
              borderBottom: "1px solid #e5e7eb",
              paddingBottom: "0.5rem",
              marginBottom: "1.5rem",
              overflowX: "auto",
            }}
          >
            {onglets.map(({ id, label, icon: Icon }) => (
              <button
                key={id}
                onClick={() => setOngletActif(id)}
                className={`tab-btn ${ongletActif === id ? "active" : ""}`}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "0.4rem",
                  padding: "0.5rem 0.75rem",
                  border: "none",
                  background:
                    ongletActif === id ? "rgba(59, 130, 246, 0.1)" : "transparent",
                  color: ongletActif === id ? "#1d4ed8" : "#374151",
                  borderRadius: "0.375rem",
                  fontSize: "0.875rem",
                  fontWeight: ongletActif === id ? "600" : "500",
                  cursor: "pointer",
                  whiteSpace: "nowrap",
                  borderBottom:
                    ongletActif === id ? "2px solid #3b82f6" : "2px solid transparent",
                }}
              >
                <Icon size={16} />
                {label}
              </button>
            ))}
          </div>

          <div>
            {ongletActif === "contexte" && <ContexteSection rapport={rapport} />}
            {ongletActif === "beneficiaires" && <BeneficiairesSection rapport={rapport} />}
            {ongletActif === "budget" && <BudgetSection rapport={rapport} />}
            {ongletActif === "execution" && <ExecutionSection rapport={rapport} />}
            {ongletActif === "remboursements" && <RemboursementsSection rapport={rapport} />}
            {ongletActif === "graphiques" && <GraphiquesSection rapport={rapport} />}
            {ongletActif === "anomalies" && (
              <AnomaliesSection exercice={rapport.exercice} actif />
            )}
            {ongletActif === "resume" && <ResumeAnalytiqueSection rapport={rapport} />}
          </div>
        </div>
      </div>
    </PageContainer>
  );
}

export default function RapportsPage() {
  return (
    <RequirePermission module="rapports">
      <RapportsContenu />
    </RequirePermission>
  );
}