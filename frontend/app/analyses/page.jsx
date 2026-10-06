"use client";

import Link from "next/link";
import { useMemo } from "react";
import {
  AlertTriangle,
  ArrowDownRight,
  ArrowRight,
  ArrowUpRight,
  BarChart3,
  Bot,
  Calculator,
  FlaskConical,
  Grid3x3,
  LineChart,
  Minus,
  Receipt,
  RefreshCcw,
  Sigma,
  TrendingUp,
  Users,
  Wallet,
} from "lucide-react";

import AnalysisSummary from "@/components/analyses/AnalysisSummary";
import StatisticalChart from "@/components/analyses/StatisticalChart";
import TemporalChart from "@/components/analyses/TemporalChart";
import StatCard from "@/components/dashboard/StatCard";
import PageContainer from "@/components/layout/PageContainer";
import Badge from "@/components/ui/Badge";
import Button from "@/components/ui/Button";
import EmptyState from "@/components/ui/EmptyState";
import Loading from "@/components/ui/Loading";
import Select from "@/components/ui/Select";
import useApercuAnalyses from "@/hooks/useApercuAnalyses";
import { usePermissions } from "@/hooks/usePermissions";
import { getApiErrorText } from "@/lib/errors";
import {
  formatCurrency,
  formatNumber,
  formatPercent,
} from "@/lib/formatters";

const MODULES = [
  {
    href: "/analyses/statistiques",
    module: "analyses",
    icon: Calculator,
    titre: "Statistiques",
    description:
      "Statistiques descriptives des dossiers de l'exercice : tendance centrale, dispersion, forme de la distribution.",
    points: [
      "Moyenne, médiane, quartiles",
      "Histogrammes et percentiles",
      "Corrélations de Pearson",
      "Actifs / pensionnés",
    ],
  },
  {
    href: "/analyses/temporelle",
    module: "analyses",
    icon: TrendingUp,
    titre: "Évolution temporelle",
    description:
      "Série mensuelle des demandes et des remboursements, comparée à l'exercice précédent.",
    points: [
      "12 mois de l'exercice",
      "Comparaison N-1",
      "Taux d'exécution mensuel",
      "Variations mois après mois",
    ],
  },
  {
    href: "/analyses/anomalies",
    module: "anomalies",
    icon: AlertTriangle,
    titre: "Détection d'anomalies",
    description:
      "Montants, délais et caractéristiques atypiques repérés dans les dossiers, à vérifier un par un.",
    points: [
      "IQR et z-score",
      "Isolation Forest, LOF",
      "Niveaux de gravité",
      "Workflow de vérification",
    ],
  },
  {
    href: "/previsions",
    module: "previsions",
    icon: LineChart,
    titre: "Prévisions",
    description:
      "Projection de la consommation par phase d'exécution, avec intervalles de confiance.",
    points: [
      "Moyenne mobile 12 mois",
      "Régression saisonnière",
      "ARIMA",
      "IC à 80 % et 95 %",
    ],
  },
  {
    href: "/simulations",
    module: "simulations",
    icon: FlaskConical,
    titre: "Simulations",
    description:
      "Évaluation de scénarios de consommation et de leur impact sur les crédits ouverts.",
    points: [
      "Scénarios prudent / central / élevé",
      "Écarts paramétrables",
      "Taux de consommation",
      "Écart au budget",
    ],
  },
  {
    href: "/assistant-ia",
    module: "assistant",
    icon: Bot,
    titre: "Assistant IA",
    description:
      "Interroger en langage naturel les indicateurs et les documents du SRB, avec les sources citées.",
    points: [
      "Routage déterministe",
      "Indicateurs déjà calculés",
      "Recherche documentaire",
      "Sources citées",
    ],
  },
];

const COMPARAISON_METRIQUES = [
  { cle: "demandes", label: "Demandes", type: "nombre" },
  { cle: "payes", label: "Dossiers payés", type: "nombre" },
  { cle: "montant_demande", label: "Montant demandé", type: "montant" },
  { cle: "montant_paye", label: "Montant remboursé", type: "montant" },
  { cle: "moyenne", label: "Montant moyen / dossier", type: "montant" },
];

const INTENSITE_VARIANT = {
  forte: "success",
  moyenne: "warning",
  faible: "neutral",
};

function formater(type, valeur) {
  return type === "montant" ? formatCurrency(valeur) : formatNumber(valeur);
}

function Ecart({ valeur, type = "nombre" }) {
  const numerique = Number(valeur);
  if (!Number.isFinite(numerique) || numerique === 0) {
    return (
      <span className="ecart ecart--nul">
        <Minus size={13} />
        stable
      </span>
    );
  }
  const absolu = Math.abs(numerique);
  const contenu =
    type === "montant"
      ? formatCurrency(absolu)
      : type === "taux"
        ? formatPercent(absolu)
        : formatNumber(absolu);
  return (
    <span className={`ecart ecart--${numerique > 0 ? "hausse" : "baisse"}`}>
      {numerique > 0 ? (
        <ArrowUpRight size={13} />
      ) : (
        <ArrowDownRight size={13} />
      )}
      {contenu}
    </span>
  );
}

function SectionTitre({ icone: Icone, titre, sousTitre, action }) {
  return (
    <div className="dash-section__header">
      <span className="dash-section__icon" aria-hidden="true">
        <Icone size={18} />
      </span>
      <div>
        <h2 className="dash-section__title">{titre}</h2>
        <p className="dash-section__subtitle">{sousTitre}</p>
      </div>
      {action}
    </div>
  );
}

function CarteComparaison({ metrique, bloc, exercicePrecedent }) {
  if (!bloc) return null;
  return (
    <div className="comparaison-card">
      <span className="comparaison-card__label">{metrique.label}</span>
      <span className="comparaison-card__valeur">
        {formater(metrique.type, bloc.courant)}
      </span>
      <span className="comparaison-card__avant">
        {formater(metrique.type, bloc.precedent)} en {exercicePrecedent}
      </span>
      <Ecart valeur={bloc.ecart} type={metrique.type} />
      {bloc.variation_pct != null && (
        <span className="comparaison-card__avant">
          {formatPercent(bloc.variation_pct)} en variation
        </span>
      )}
    </div>
  );
}

function Correlations({ correlations, variables }) {
  if (!correlations || correlations.length === 0) return null;
  return (
    <div className="card card__padding">
      <h3 className="chart-card__title">Relations les plus marquées</h3>
      <p className="chart-card__subtitle">
        Coefficients de Pearson entre montants, délais et âge du bénéficiaire
      </p>
      <ul className="correlation-list">
        {correlations.map((paire) => (
          <li key={`${paire.a}-${paire.b}`} className="correlation-item">
            <div className="correlation-item__gauche">
              <span className="correlation-item__libelle">
                {variables?.[paire.a] || paire.a}
                <span className="correlation-item__fleche">↔</span>
                {variables?.[paire.b] || paire.b}
              </span>
              <div className="correlation-item__barre">
                <span
                  className={`correlation-item__remplissage correlation-item__remplissage--${paire.correlation >= 0 ? "positif" : "negatif"}`}
                  style={{
                    width: `${Math.min(Math.abs(paire.correlation), 1) * 100}%`,
                  }}
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

function ComparaisonSituation({ bloc }) {
  const comparaison = bloc?.comparaison || [];
  if (comparaison.length === 0) return null;
  return (
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
  );
}

export default function AnalysesPage() {
  const {
    exercices,
    exercice,
    setExercice,
    temporelle,
    statistiques,
    loading,
    error,
    recharger,
  } = useApercuAnalyses();

  const { canAccessModule } = usePermissions();

  const modulesVisibles = useMemo(
    () => MODULES.filter((module) => canAccessModule(module.module)),
    [canAccessModule]
  );

  const synthese = temporelle?.synthese;
  const comparaison = temporelle?.comparaison;
  const exercicePrecedent = comparaison?.exercice_precedent;
  const descriptives = statistiques?.descriptives;

  const nombreDossiers = statistiques?.nombre_documents ?? null;
  const aucunDossier =
    statistiques != null && (nombreDossiers ?? 0) === 0;

  const correlations = useMemo(
    () => (statistiques?.correlations?.pertinentes || []).slice(0, 5),
    [statistiques]
  );

  const enCours = loading && !temporelle && !statistiques;
  const sansExercice = !loading && !error && exercices.length === 0;

  return (
    <PageContainer
      title="Analyses"
      subtitle="Analyse des données RFM : population bénéficiaire, dossiers de remboursement et exécution"
      actions={
        <>
          {exercices.length > 1 && (
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
          )}
          {exercice != null && (
            <Button
              variant="outline"
              onClick={recharger}
              disabled={loading}
              aria-label="Recharger les analyses"
            >
              <RefreshCcw size={15} />
              Actualiser
            </Button>
          )}
        </>
      }
    >
      {enCours && <Loading label="Calcul des analyses…" />}

      {error && !temporelle && !statistiques && (
        <div className="card card__padding">
          <EmptyState
            icon={BarChart3}
            title="Impossible de charger les analyses"
            description={getApiErrorText(error)}
            action={
              <Button variant="primary" onClick={recharger}>
                <RefreshCcw size={15} />
                Réessayer
              </Button>
            }
          />
        </div>
      )}

      {sansExercice && (
        <div className="card card__padding">
          <EmptyState
            icon={BarChart3}
            title="Aucun exercice analysable"
            description="Le backend ne renvoie aucun exercice pour le moment. Amorcez la base (backend/scripts/seed.py) ou importez des dossiers de remboursement depuis le module d'importation."
            action={
              <Link href="/imports" className="btn btn--primary btn--md">
                Importer des données
              </Link>
            }
          />
        </div>
      )}

      <section className="dash-section">
        <SectionTitre
          icone={Grid3x3}
          titre="Modules d'analyse"
          sousTitre="Chaque module utilise des méthodes et des indicateurs distincts ; les résultats sont calculés par le backend"
        />
        <div className="features-grid">
          {modulesVisibles.map((module) => (
            <Link
              key={module.href}
              href={module.href}
              className="feature-card module-card"
            >
              <span className="feature-card__icon" aria-hidden="true">
                <module.icon size={22} />
              </span>
              <span className="feature-card__title">{module.titre}</span>
              <span className="feature-card__text">{module.description}</span>
              <ul className="module-card__points">
                {module.points.map((point) => (
                  <li key={point}>{point}</li>
                ))}
              </ul>
              <span className="module-card__footer">
                Ouvrir le module <ArrowRight size={14} />
              </span>
            </Link>
          ))}
        </div>
      </section>

      {(temporelle || statistiques) && !sansExercice && (
        <>
          {aucunDossier ? (
            <section className="dash-section">
              <div className="card card__padding">
                <EmptyState
                  icon={Receipt}
                  title={`Aucun dossier de remboursement sur l'exercice ${exercice}`}
                  description="Les indicateurs de l'exercice sont vides. Vérifiez la période de dépôt des dossiers ou changez d'exercice."
                />
              </div>
            </section>
          ) : (
            <>
              {synthese && (
                <section className="dash-section">
                  <SectionTitre
                    icone={BarChart3}
                    titre={`Aperçu de l'exercice ${exercice}`}
                    sousTitre="Indicateurs calculés par le backend sur les dossiers déposés"
                    action={
                      loading ? <Badge variant="info" dot>Actualisation…</Badge> : null
                    }
                  />
                  <div className="dash-grid dash-grid--md">
                    <StatCard
                      icon={Receipt}
                      label="Dossiers déposés"
                      value={formatNumber(synthese.demandes)}
                      sub={`${formatNumber(nombreDossiers)} dossiers analysés`}
                    />
                    <StatCard
                      icon={Receipt}
                      label="Dossiers payés"
                      value={formatNumber(synthese.payes)}
                      sub="remboursements réglés"
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
                      variant={
                        (synthese.taux_execution ?? 0) >= 0.8
                          ? "success"
                          : (synthese.taux_execution ?? 0) >= 0.5
                            ? "warning"
                            : "danger"
                      }
                    />
                    <StatCard
                      icon={Wallet}
                      label="Montant moyen / dossier"
                      value={formatCurrency(synthese.moyenne)}
                      sub="sur l'ensemble des demandes"
                    />
                    <StatCard
                      icon={Sigma}
                      label="Montant médian"
                      value={formatCurrency(descriptives?.montant_demande?.mediane)}
                      sub="plus sensible aux valeurs extrêmes"
                      variant="info"
                    />
                    <StatCard
                      icon={TrendingUp}
                      label="Délai moyen"
                      value={`${formatNumber(descriptives?.delai_jours?.moyenne)} j`}
                      sub={`médiane ${formatNumber(descriptives?.delai_jours?.mediane)} j`}
                      variant="warning"
                    />
                    <StatCard
                      icon={Users}
                      label="Âge moyen"
                      value={`${formatNumber(descriptives?.age_beneficiaire?.moyenne)} ans`}
                      sub={`médiane ${formatNumber(descriptives?.age_beneficiaire?.mediane)} ans`}
                      variant="info"
                    />
                    <StatCard
                      icon={BarChart3}
                      label="Moyenne mensuelle"
                      value={formatCurrency(synthese.moyenne_mensuelle?.montant_demande)}
                      sub={`${formatNumber(synthese.moyenne_mensuelle?.demandes)} dossiers / mois`}
                    />
                  </div>
                </section>
              )}

              <AnalysisSummary
                temporelle={temporelle}
                statistiques={statistiques}
              />

              {comparaison && (
                <section className="dash-section">
                  <SectionTitre
                    icone={ArrowUpRight}
                    titre={`Comparaison avec l'exercice ${exercicePrecedent}`}
                    sousTitre="Écarts et variations de l'exercice sélectionné"
                  />
                  <div className="comparaison-grid">
                    {COMPARAISON_METRIQUES.map((metrique) => (
                      <CarteComparaison
                        key={metrique.cle}
                        metrique={metrique}
                        bloc={comparaison[metrique.cle]}
                        exercicePrecedent={exercicePrecedent}
                      />
                    ))}
                    <div className="comparaison-card">
                      <span className="comparaison-card__label">
                        Taux d'exécution
                      </span>
                      <span className="comparaison-card__valeur">
                        {formatPercent(comparaison.taux_execution?.courant)}
                      </span>
                      <span className="comparaison-card__avant">
                        {formatPercent(comparaison.taux_execution?.precedent)} en{" "}
                        {exercicePrecedent}
                      </span>
                      <Ecart
                        valeur={comparaison.taux_execution?.ecart}
                        type="taux"
                      />
                    </div>
                  </div>
                </section>
              )}

              <section className="dash-section">
                <SectionTitre
                  icone={TrendingUp}
                  titre="Dynamique de l'exercice"
                  sousTitre="Série mensuelle et forme de la distribution des montants"
                />
                <div className="dashboard-charts">
                  <TemporalChart evolution={temporelle?.evolution} />
                  <StatisticalChart
                    classes={statistiques?.distributions?.montant_demande}
                    titre="Distribution des montants demandés"
                    couleur="#0891b2"
                  />
                  <StatisticalChart
                    classes={statistiques?.distributions?.montant_paye}
                    titre="Distribution des montants remboursés"
                    couleur="#d97706"
                  />
                </div>
              </section>

              {correlations.length > 0 && (
                <section className="dash-section">
                  <SectionTitre
                    icone={Grid3x3}
                    titre="Relations entre variables"
                    sousTitre="Corrélations de Pearson retenues par le backend"
                  />
                  <Correlations
                    correlations={correlations}
                    variables={statistiques?.variables}
                  />
                </section>
              )}

              {statistiques?.actifs_pensionnes && (
                <section className="dash-section">
                  <SectionTitre
                    icone={Users}
                    titre="Actifs et pensionnés"
                    sousTitre={
                      statistiques.actifs_pensionnes.effectifs_population
                        ? `${formatNumber(statistiques.actifs_pensionnes.effectifs_population.actif)} bénéficiaires actifs et ${formatNumber(statistiques.actifs_pensionnes.effectifs_population.pensionne)} pensionnés enregistrés`
                        : "Comparaison des deux situations administratives"
                    }
                  />
                  <ComparaisonSituation bloc={statistiques.actifs_pensionnes} />
                </section>
              )}
            </>
          )}
        </>
      )}
    </PageContainer>
  );
}
