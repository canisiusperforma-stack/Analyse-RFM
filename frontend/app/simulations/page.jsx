"use client";

import { Calculator, CircleHelp, FlaskConical, Info, RefreshCcw } from "lucide-react";

import StatCard from "@/components/dashboard/StatCard";
import PageContainer from "@/components/layout/PageContainer";
import Button from "@/components/ui/Button";
import Badge from "@/components/ui/Badge";
import Select from "@/components/ui/Select";
import useSimulations from "@/hooks/useSimulations";
import { usePermissions } from "@/hooks/usePermissions";
import { getApiErrorText } from "@/lib/errors";
import { formatCurrency, formatNumber, formatPercent } from "@/lib/formatters";

const SITUATION_VARIANTS = {
  dans_le_budget: "success",
  depassement: "danger",
  sans_budget: "neutral",
};

const SITUATION_LABELS = {
  dans_le_budget: "Dans le budget",
  depassement: "Dépassement",
  sans_budget: "Sans budget",
};

const OPTIONS_ECART = [5, 10, 15, 20, 25].map((valeur) => ({
  value: valeur,
  label: `${valeur} %`,
}));

function Avertissement({ texte }) {
  return (
    <div
      className="card card__padding"
      style={{
        display: "flex",
        gap: 12,
        alignItems: "flex-start",
        border: "1px solid var(--c-border, #e5e7eb)",
      }}
    >
      <CircleHelp size={18} style={{ color: "#b45309", flexShrink: 0 }} />
      <p style={{ margin: 0, lineHeight: 1.6 }}>{texte}</p>
    </div>
  );
}

function ChampNombre({ label, valeur, onChange, placeholder, suffixe, id }) {
  return (
    <div className="filtres-bar__champ">
      <label className="field__label" htmlFor={id}>
        {label}
      </label>
      <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
        <input
          id={id}
          type="number"
          min="0"
          step="any"
          className="input"
          placeholder={placeholder}
          value={valeur}
          onChange={(evenement) => onChange(evenement.target.value)}
        />
        {suffixe && <span className="tableau__sous-texte">{suffixe}</span>}
      </div>
    </div>
  );
}

export default function SimulationsPage() {
  const {
    referentiel,
    hypotheses,
    modifieHypotheses,
    resultat,
    loading,
    error,
    calculer,
    reinitialiser,
    hypothesesValides,
  } = useSimulations();

  const permissions = usePermissions();
  const canCalculer = permissions.has("simulations:creer");

  const lancer = async () => {
    try {
      await calculer();
    } catch {
      // l'erreur est exposée via error
    }
  };

  const reference = resultat?.reference;
  const avertissement =
    resultat?.avertissement || referentiel?.avertissement;

  return (
    <PageContainer
      title="Simulateur budgétaire"
      subtitle="Budget hypothétique + nombre de dossiers + montant moyen → consommation estimée"
      actions={
        <span className="badge" title="Simples dossiers × montant moyen">
          <Calculator size={13} /> dossiers × montant moyen
        </span>
      }
    >
      <section className="conv-section conv-section--filtres">
        <div className="conv-section__header">
          <span className="conv-section__icon">
            <FlaskConical size={18} />
          </span>
          <div>
            <h2 className="conv-section__title">Hypothèses</h2>
            <p className="conv-section__subtitle">
              Le simulateur estime une consommation « nombre de dossiers ×
              montant moyen » et la confronte à un budget hypothétique selon
              trois scénarios : prudent, intermédiaire, élevé.
            </p>
          </div>
        </div>

        <div className="filtres-bar" style={{ marginTop: 12 }}>
          <ChampNombre
            id="budget-hypothetique"
            label="Budget hypothétique (Ar)"
            valeur={hypotheses.budgetHypothetique}
            onChange={(valeur) =>
              modifieHypotheses({ budgetHypothetique: valeur })
            }
            placeholder="Ex. 3289817617"
          />
          <ChampNombre
            id="nombre-dossiers"
            label="Nombre de dossiers"
            valeur={hypotheses.nombreDossiers}
            onChange={(valeur) =>
              modifieHypotheses({ nombreDossiers: valeur })
            }
            placeholder="Ex. 15000"
          />
          <ChampNombre
            id="montant-moyen"
            label="Montant moyen par dossier (Ar)"
            valeur={hypotheses.montantMoyen}
            onChange={(valeur) =>
              modifieHypotheses({ montantMoyen: valeur })
            }
            placeholder="Ex. 200000"
          />
          <div className="filtres-bar__champ">
            <Select
              label="Écart dossiers entre scénarios"
              value={hypotheses.ecartDossiersPct}
              onChange={(evenement) =>
                modifieHypotheses({
                  ecartDossiersPct: Number(evenement.target.value),
                })
              }
              options={OPTIONS_ECART}
            />
          </div>
          <div className="filtres-bar__champ">
            <Select
              label="Écart montant entre scénarios"
              value={hypotheses.ecartMontantPct}
              onChange={(evenement) =>
                modifieHypotheses({
                  ecartMontantPct: Number(evenement.target.value),
                })
              }
              options={OPTIONS_ECART}
            />
          </div>
        </div>

        <div
          style={{
            display: "flex",
            gap: 8,
            marginTop: 12,
            alignItems: "center",
          }}
        >
          {canCalculer ? (
            <>
              <Button
                onClick={lancer}
                loading={loading}
                disabled={loading || !hypothesesValides}
              >
                <Calculator size={15} />
                Calculer les scénarios
              </Button>
              <Button variant="ghost" onClick={reinitialiser} disabled={loading}>
                <RefreshCcw size={15} />
                Réinitialiser
              </Button>
            </>
          ) : (
            <Badge variant="neutral" dot>
              Lecture seule
            </Badge>
          )}
          <Info size={14} />
          <span className="tableau__sous-texte">
            Les scénarios sont des hypothèses de travail, pas des prédictions
            certaines.
          </span>
        </div>
      </section>

      {error && (
        <div className="card card__padding" style={{ marginBottom: 16 }}>
          <p className="field__error">{getApiErrorText(error)}</p>
        </div>
      )}

      {avertissement && (
        <section className="conv-section">
          <Avertissement texte={avertissement} />
        </section>
      )}

      {resultat && reference && (
        <section className="conv-section">
          <div className="conv-section__header">
            <span className="conv-section__icon">
              <Calculator size={18} />
            </span>
            <div>
              <h2 className="conv-section__title">
                Résultats par scénario
              </h2>
              <p className="conv-section__subtitle">
                Consommation estimée = nombre de dossiers × montant moyen, avec
                écarts de {resultat.ecarts_pct.dossiers} % sur les dossiers et{" "}
                {resultat.ecarts_pct.montant} % sur le montant moyen
              </p>
            </div>
          </div>

          <div className="dash-grid" style={{ marginTop: 12 }}>
            <StatCard
              icon={FlaskConical}
              label="Budget hypothétique"
              value={formatCurrency(reference.budget_hypothetique)}
              sub="disponible pour la période"
            />
            <StatCard
              icon={Calculator}
              label="Consommation centrale"
              value={formatCurrency(reference.consommation_centrale)}
              sub={`${formatNumber(reference.nombre_dossiers)} dossiers × ${formatCurrency(reference.montant_moyen)}`}
              variant={reference.situation_centrale === "depassement" ? "danger" : "default"}
            />
            <StatCard
              icon={Info}
              label="Taux de consommation"
              value={
                reference.taux_consommation_central != null
                  ? formatPercent(reference.taux_consommation_central)
                  : "—"
              }
              sub={
                <Badge
                  variant={SITUATION_VARIANTS[reference.situation_centrale]}
                  dot
                >
                  {SITUATION_LABELS[reference.situation_centrale]}
                </Badge>
              }
            />
          </div>

          <div className="dash-grid" style={{ marginTop: 16 }}>
            {resultat.scenarios.map((scenario) => {
              const depassement = scenario.situation === "depassement";
              return (
                <div className="card card__padding" key={scenario.cle}>
                  <div
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "center",
                      gap: 8,
                    }}
                  >
                    <h3 className="chart-card__title" style={{ margin: 0 }}>
                      Scénario « {scenario.libelle} »
                    </h3>
                    <Badge
                      variant={SITUATION_VARIANTS[scenario.situation]} dot
                    >
                      {SITUATION_LABELS[scenario.situation]}
                    </Badge>
                  </div>
                  <p className="chart-card__subtitle">
                    {scenario.sous_hypothese}
                  </p>
                  <p
                    className="chart-card__title"
                    style={{
                      fontSize: "1.35rem",
                      margin: "12px 0 4px",
                      color: depassement ? "var(--c-danger, #dc2626)" : "inherit",
                    }}
                  >
                    {formatCurrency(scenario.consommation_estimee)}
                  </p>
                  <p className="chart-card__subtitle" style={{ margin: 0 }}>
                    {formatNumber(scenario.nombre_dossiers)} dossiers ×{" "}
                    {formatCurrency(scenario.montant_moyen)}
                  </p>
                  <p className="tableau__sous-texte" style={{ marginTop: 8 }}>
                    Taux :{" "}
                    {scenario.taux_consommation != null
                      ? formatPercent(scenario.taux_consommation)
                      : "—"}{" "}
                    · Écart budget :{" "}
                    {scenario.ecart_budget >= 0 ? "excédent " : "dépassement "}
                    {formatCurrency(Math.abs(scenario.ecart_budget))}
                  </p>
                </div>
              );
            })}
          </div>

          <div className="card card__padding" style={{ marginTop: 16 }}>
            <h3 className="chart-card__title">Comparaison des scénarios</h3>
            <div className="tableau tableau--scroll" style={{ marginTop: 12 }}>
              <table className="tableau__table">
                <thead>
                  <tr>
                    <th>Scénario</th>
                    <th>Dossiers</th>
                    <th>Montant moyen</th>
                    <th>Consommation estimée</th>
                    <th>Taux</th>
                    <th>Écart budget</th>
                    <th>Situation</th>
                  </tr>
                </thead>
                <tbody>
                  {resultat.scenarios.map((scenario) => (
                    <tr key={scenario.cle}>
                      <td className="tableau__nom">
                        {scenario.libelle}
                        <span
                          className="tableau__sous-texte"
                          style={{ display: "block" }}
                        >
                          {scenario.sous_hypothese}
                        </span>
                      </td>
                      <td className="tableau__montant">
                        {formatNumber(scenario.nombre_dossiers)}
                      </td>
                      <td className="tableau__montant">
                        {formatCurrency(scenario.montant_moyen)}
                      </td>
                      <td className="tableau__montant">
                        {formatCurrency(scenario.consommation_estimee)}
                      </td>
                      <td className="tableau__montant">
                        {scenario.taux_consommation != null
                          ? formatPercent(scenario.taux_consommation)
                          : "—"}
                      </td>
                      <td className="tableau__montant">
                        {scenario.ecart_budget >= 0 ? "−" : "+"}
                        {formatCurrency(Math.abs(scenario.ecart_budget))}
                      </td>
                      <td>
                        <Badge
                          variant={SITUATION_VARIANTS[scenario.situation]} dot
                        >
                          {SITUATION_LABELS[scenario.situation]}
                        </Badge>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="chart-card__subtitle" style={{ marginTop: 12 }}>
              Le scénario « élevé » présente l&apos;hypothèse la plus
              défavorable : s&apos;il dépasse le budget, la prévision centrale
              doit être considérée avec prudence.
            </p>
          </div>
        </section>
      )}
    </PageContainer>
  );
}