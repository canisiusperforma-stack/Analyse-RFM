"use client";

import { useState } from "react";
import {
  CalendarRange,
  Database,
  ListChecks,
  LineChart,
  Sparkles,
  TrendingUp,
  TriangleAlert,
  X,
} from "lucide-react";
import {
  Area,
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
import Button from "@/components/ui/Button";
import Badge from "@/components/ui/Badge";
import EmptyState from "@/components/ui/EmptyState";
import Loading from "@/components/ui/Loading";
import Select from "@/components/ui/Select";
import usePrevisions from "@/hooks/usePrevisions";
import { usePermissions } from "@/hooks/usePermissions";
import { getApiErrorText } from "@/lib/errors";
import {
  compactCurrency,
  formatCurrency,
  formatDateTime,
  formatNumber,
  formatPercent,
} from "@/lib/formatters";

const SUFFISANCE_VARIANTS = {
  suffisant: "success",
  limite: "warning",
  insuffisant: "danger",
};

function construireDonneesChart(resultat) {
  const historique = (resultat.serie_mensuelle || []).map((point) => ({
    mois: point.mois,
    reel: point.valeur,
  }));
  const meilleur = (resultat.previsions || []).find((m) => m.meilleur);
  const prevus = (meilleur?.valeurs || []).map((point) => ({
    mois: point.mois,
    prevu: point.valeur,
    bas80: point.bas_80,
    haut80: point.haut_80,
  }));
  return [...historique, ...prevus];
}

function ChartPrevision({ resultat }) {
  const donnees = construireDonneesChart(resultat);
  return (
    <div className="card card__padding chart-card" style={{ marginTop: 16 }}>
      <h3 className="chart-card__title">
        Consommation mensuelle et prévision du modèle retenu
      </h3>
      <p className="chart-card__subtitle">
        Historique observé, prévision centrale et intervalle à 80 % (bande
        claire) — trajectoire indicative
      </p>
      <div className="chart-card__body">
        <ResponsiveContainer width="100%" height={300}>
          <ComposedChart
            data={donnees}
            margin={{ top: 8, right: 8, left: 0, bottom: 0 }}
          >
            <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
            <XAxis dataKey="mois" tick={{ fontSize: 10 }} />
            <YAxis
              tick={{ fontSize: 11 }}
              width={64}
              tickFormatter={compactCurrency}
              domain={["auto", "auto"]}
            />
            <Tooltip
              formatter={(valeur, nom) => [formatCurrency(valeur), nom]}
              labelStyle={{ fontWeight: 600 }}
            />
            <Legend wrapperStyle={{ fontSize: 12 }} />
            <Area
              type="monotone"
              dataKey="bas80"
              name="Borne basse (80 %)"
              stackId="ci"
              stroke="none"
              fill="transparent"
              tooltipType="none"
            />
            <Area
              type="monotone"
              dataKey="haut80"
              name="Intervalle 80 %"
              stackId="ci"
              stroke="none"
              fill="#93c5fd"
              fillOpacity={0.4}
              tooltipType="none"
            />
            <Line
              type="monotone"
              dataKey="reel"
              name="Observé"
              stroke="#2563eb"
              strokeWidth={2}
              connectNulls
              dot={false}
            />
            <Line
              type="monotone"
              dataKey="prevu"
              name="Prévision (modèle retenu)"
              stroke="#16a34a"
              strokeWidth={2}
              strokeDasharray="6 3"
              dot={{ r: 3 }}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

function TableauMetriques({ resultat }) {
  return (
    <div className="card card__padding" style={{ marginTop: 16 }}>
      <h3 className="chart-card__title">Comparaison des modèles</h3>
      <p className="chart-card__subtitle">
        Métriques sur les {resultat.test_size} derniers mois réservés
        (validation) — classement par RMSE puis MAE, MAPE en %
      </p>
      <div className="tableau tableau--scroll" style={{ marginTop: 12 }}>
        <table className="tableau__table">
          <thead>
            <tr>
              <th>Modèle</th>
              <th>Applicabilité</th>
              <th>RMSE</th>
              <th>MAE</th>
              <th>MAPE</th>
              <th>R²</th>
            </tr>
          </thead>
          <tbody>
            {resultat.modeles_essayes.map((modele) => {
              const metrique = resultat.metriques?.find(
                (m) => m.modele === modele.cle
              );
              return (
                <tr key={modele.cle}>
                  <td className="tableau__nom">
                    {modele.label}
                    {metrique?.meilleur && (
                      <>
                        {" "}
                        <Badge variant="success" dot>
                          Meilleur
                        </Badge>
                      </>
                    )}
                  </td>
                  <td>
                    {modele.applique ? (
                      <Badge variant="success" dot>
                        Appliqué
                      </Badge>
                    ) : (
                      <span className="tableau__sous-texte">{modele.raison}</span>
                    )}
                  </td>
                  <td className="tableau__montant">
                    {metrique ? formatNumber(metrique.rmse) : "—"}
                  </td>
                  <td className="tableau__montant">
                    {metrique ? formatNumber(metrique.mae) : "—"}
                  </td>
                  <td className="tableau__montant">
                    {metrique?.mape != null
                      ? formatPercent(metrique.mape / 100)
                      : "—"}
                  </td>
                  <td className="tableau__montant">
                    {metrique?.r2 != null ? formatNumber(metrique.r2) : "—"}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function TableauPrevisions({ resultat }) {
  const appliques = (resultat.previsions || []).filter(
    (m) => m.applique && m.valeurs.length > 0
  );
  if (appliques.length === 0) return null;
  const mois = appliques[0].valeurs.map((v) => v.mois);
  return (
    <div className="card card__padding" style={{ marginTop: 16 }}>
      <h3 className="chart-card__title">Prévisions par modèle (mois)</h3>
      <p className="chart-card__subtitle">
        Valeur centrale et intervalle à 95 % pour chacun des {mois.length} mois
        prévus
      </p>
      <div className="tableau tableau--scroll" style={{ marginTop: 12 }}>
        <table className="tableau__table">
          <thead>
            <tr>
              <th>Modèle</th>
              {mois.map((m) => (
                <th key={m}>
                  {m.slice(5)}/{m.slice(2, 4)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {appliques.map((modele) => (
              <tr key={modele.modele}>
                <td className="tableau__nom">
                  {modele.label}
                  {modele.meilleur && (
                    <>
                      {" "}
                      <Badge variant="success" dot>
                        Retenu
                      </Badge>
                    </>
                  )}
                </td>
                {modele.valeurs.map((point) => (
                  <td key={point.mois}>
                    <span className="tableau__montant">
                      {formatNumber(point.valeur)}
                    </span>
                    <div className="tableau__sous-texte">
                      [{compactCurrency(point.bas_95)} ; {compactCurrency(point.haut_95)}]
                    </div>
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

export default function PrevisionsPage() {
  const {
    referentiel,
    donnees,
    resultat,
    parametres,
    modifieParametres,
    loadingDonnees,
    generationLoading,
    error,
    generationError,
    lancerGeneration,
    setResultat,
  } = usePrevisions();

  const permissions = usePermissions();
  const canGenerer = permissions.has("previsions:creer");

  const optionsHorizon = Array.from({ length: 12 }, (_, i) => ({
    value: i + 1,
    label: `${i + 1} mois`,
  }));
  const optionsMethode = [
    { value: "", label: "Tous les modèles" },
    ...(referentiel?.modeles || []).map((modele) => ({
      value: modele.cle,
      label: modele.libelle,
    })),
  ];

  const lancer = async () => {
    try {
      await lancerGeneration();
    } catch {
      // l'erreur est exposée via generationError
    }
  };

  const meilleur = (resultat?.previsions || []).find((m) => m.meilleur);
  const totalPrevu =
    meilleur?.applique && meilleur.valeurs
      ? meilleur.valeurs.reduce((somme, v) => somme + v.valeur, 0)
      : null;
  const suffisance = resultat?.suffisance;

  return (
    <PageContainer
      title="Prévisions budgétaires"
      subtitle="Prévision de la consommation du budget RFM à partir des exécutions mensuelles"
      actions={
        <>
          <Select
            label="Phase"
            value={parametres.phase}
            onChange={(evenement) =>
              modifieParametres({ phase: evenement.target.value })
            }
            options={(referentiel?.phases || []).map((phase) => ({
              value: phase.cle,
              label: phase.libelle,
            }))}
            disabled={generationLoading}
          />
          <Select
            label="Horizon"
            value={parametres.horizon}
            onChange={(evenement) =>
              modifieParametres({ horizon: Number(evenement.target.value) })
            }
            options={optionsHorizon}
            disabled={generationLoading}
          />
          <Select
            label="Modèle"
            value={parametres.methode}
            onChange={(evenement) =>
              modifieParametres({ methode: evenement.target.value })
            }
            options={optionsMethode}
            disabled={generationLoading}
          />
          {canGenerer ? (
            <Button
              onClick={lancer}
              loading={generationLoading}
              disabled={generationLoading || !donnees?.points}
            >
              <TrendingUp size={15} />
              Générer la prévision
            </Button>
          ) : (
            <Badge variant="neutral" dot>
              Lecture seule
            </Badge>
          )}
        </>
      }
    >
      <section className="conv-section">
        <div className="conv-section__header">
          <span className="conv-section__icon">
            <Database size={18} />
          </span>
          <div>
            <h2 className="conv-section__title">Données disponibles</h2>
            <p className="conv-section__subtitle">
              Historique mensuel de la phase «{" "}
              {(referentiel?.phases || []).find(
                (p) => p.cle === parametres.phase
              )?.libelle || parametres.phase} » — les prévisions reposent sur
              cette quantité de données
            </p>
          </div>
        </div>
        {loadingDonnees ? (
          <Loading />
        ) : donnees && donnees.points > 0 ? (
          <div className="dash-grid" style={{ marginTop: 12 }}>
            <StatCard
              icon={LineChart}
              label="Points mensuels"
              value={formatNumber(donnees.points)}
              sub={`du ${donnees.premier_mois} au ${donnees.dernier_mois}`}
            />
            <StatCard
              icon={CalendarRange}
              label="Exercices couverts"
              value={formatNumber(donnees.exercices.length)}
              sub={donnees.exercices.join(", ")}
            />
            <StatCard
              icon={Sparkles}
              label="Modèles comparés"
              value={formatNumber(referentiel?.modeles?.length || 0)}
              sub="moyenne mobile, régression, ARIMA…"
            />
          </div>
        ) : (
          <EmptyState
            title="Aucune exécution mensuelle"
            description="Aucune exécution mensuelle disponible pour cette phase."
            icon={Database}
          />
        )}
      </section>

      {error && (
        <div className="card card__padding" style={{ marginBottom: 16 }}>
          <p className="field__error">{getApiErrorText(error)}</p>
        </div>
      )}

      {generationLoading && (
        <section className="conv-section">
          <Loading label="Comparaison des modèles et calcul des prévisions…" />
        </section>
      )}

      {resultat && suffisance && (
        <section className="conv-section">
          <div className="conv-section__header">
            <span className="conv-section__icon">
              <TrendingUp size={18} />
            </span>
            <div>
              <h2 className="conv-section__title">
                Prévision {resultat.libelle_phase.toLowerCase()} —{" "}
                {resultat.horizon} mois
              </h2>
              <p className="conv-section__subtitle">
                Calculée le {formatDateTime(resultat.calcule_le)} ·{" "}
                {resultat.points_mensuels} points mensuels ·{" "}
                {resultat.exercices.join(", ")}
              </p>
            </div>
            <button
              type="button"
              className="icon-btn"
              onClick={() => setResultat(null)}
              aria-label="Fermer le résultat de prévision"
            >
              <X size={18} />
            </button>
          </div>

          <div className="card card__padding" style={{ marginTop: 16 }}>
            <div
              style={{
                display: "flex",
                gap: 12,
                alignItems: "flex-start",
              }}
            >
              <span style={{ marginTop: 2, color: "#b45309" }}>
                <TriangleAlert size={18} />
              </span>
              <div>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <h3 className="chart-card__title" style={{ margin: 0 }}>
                    {suffisance.libelle}
                  </h3>
                  <Badge
                    variant={SUFFISANCE_VARIANTS[suffisance.niveau] || "neutral"}
                    dot
                  >
                    {suffisance.suffisant
                      ? "Robuste"
                      : "Expérimental / indicatif"}
                  </Badge>
                </div>
                <p className="chart-card__subtitle" style={{ marginTop: 6 }}>
                  {suffisance.raison}
                </p>
              </div>
            </div>
          </div>

          {suffisance.niveau !== "insuffisant" && (
            <>
              <div className="dash-grid" style={{ marginTop: 16 }}>
                <StatCard
                  icon={Sparkles}
                  label="Modèle retenu"
                  value={meilleur?.label}
                  sub={resultat.interpretation}
                />
                <StatCard
                  icon={TrendingUp}
                  label="Consommation prévue (horizon)"
                  value={totalPrevu ? formatCurrency(totalPrevu) : "—"}
                  sub={`sur les ${resultat.horizon} prochains mois`}
                />
                <StatCard
                  icon={ListChecks}
                  label="Fenêtre de validation"
                  value={`${resultat.test_size} mois`}
                  sub="réservés à la comparaison des modèles"
                />
              </div>

              <ChartPrevision resultat={resultat} />
              <TableauMetriques resultat={resultat} />
              <TableauPrevisions resultat={resultat} />

              <div className="card card__padding" style={{ marginTop: 16 }}>
                <h3 className="chart-card__title">
                  Limites et précautions
                </h3>
                <ul style={{ margin: "8px 0 0 18px", lineHeight: 1.6 }}>
                  {resultat.limites.map((limite) => (
                    <li key={limite}>{limite}</li>
                  ))}
                </ul>
              </div>
            </>
          )}
        </section>
      )}

      {generationError && (
        <div className="card card__padding" style={{ marginTop: 16 }}>
          <p className="field__error">{getApiErrorText(generationError)}</p>
        </div>
      )}
    </PageContainer>
  );
}