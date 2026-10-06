"use client";

import { useState } from "react";
import {
  AlertTriangle,
  Layers,
  RefreshCcw,
  ScanSearch,
  Search,
  ShieldAlert,
  X,
} from "lucide-react";

import StatCard from "@/components/dashboard/StatCard";
import AnomalieDetailModal from "@/components/anomalies/AnomalieDetailModal";
import AnomalieTable from "@/components/anomalies/AnomalieTable";
import PageContainer from "@/components/layout/PageContainer";
import Badge from "@/components/ui/Badge";
import Button from "@/components/ui/Button";
import Select from "@/components/ui/Select";
import useAnomalies from "@/hooks/useAnomalies";
import { usePermissions } from "@/hooks/usePermissions";
import { METHODE_LABELS } from "@/lib/anomalies";
import { getApiErrorText } from "@/lib/errors";
import { formatDateTime, formatNumber } from "@/lib/formatters";

const TRI_OPTIONS = [
  { value: "detecte_le", label: "Date de détection" },
  { value: "score", label: "Score" },
  { value: "valeur", label: "Valeur" },
  { value: "niveau", label: "Niveau" },
  { value: "numero_dossier", label: "N° de dossier" },
];

export default function AnomaliesPage() {
  const {
    exercices,
    exercice,
    setExercice,
    referentiel,
    liste,
    filtres,
    modifieFiltres,
    reinitialiserFiltres,
    saut,
    setSaut,
    limite,
    loading,
    error,
    recharger,
    detection,
    detectionLoading,
    detectionError,
    lancerDetection,
    fermerDetection,
  } = useAnomalies();

  const permissions = usePermissions();
  const canTraiter = permissions.has("anomalies:traiter");

  const [selection, setSelection] = useState(null);

  const statutsOptions =
    referentiel?.statuts_verification?.map((item) => ({
      value: item.cle,
      label: item.label,
    })) || [];
  const niveauxOptions =
    referentiel?.niveaux?.map((item) => ({
      value: item.cle,
      label: item.label,
    })) || [];
  const methodesOptions =
    referentiel?.methodes?.map((item) => ({
      value: item.cle,
      label: item.label,
    })) || [];
  const variablesOptions =
    referentiel?.variables?.map((item) => ({
      value: item.cle,
      label: item.label,
    })) || [];

  const filtresActifs =
    filtres.recherche.trim() !== "" ||
    filtres.statut_verification !== "" ||
    filtres.niveau !== "" ||
    filtres.methode !== "" ||
    filtres.variable !== "" ||
    filtres.tri !== "detecte_le" ||
    filtres.ordre !== "desc";

  const lancer = async () => {
    try {
      await lancerDetection();
    } catch {
      // l'erreur est exposée via detectionError
    }
  };

  const majSelection = (miseAJour) => {
    setSelection(miseAJour);
    setListe((precedente) => {
      if (!precedente) return precedente;
      return {
        ...precedente,
        items: precedente.items.map((item) =>
          item.id === miseAJour.id ? miseAJour : item
        ),
      };
    });
  };

  return (
    <PageContainer
      title="Détection d'anomalies"
      subtitle="Observations atypiques et valeurs à vérifier dans les remboursements"
      actions={
        <>
          {exercices.length > 0 && (
            <Select
              label="Exercice"
              value={exercice ?? ""}
              onChange={(evenement) =>
                setExercice(
                  evenement.target.value
                    ? Number(evenement.target.value)
                    : null
                )
              }
              options={[
                { value: "", label: "Tous les exercices" },
                ...exercices.map((annee) => ({
                  value: annee,
                  label: `Exercice ${annee}`,
                })),
              ]}
              disabled={loading}
            />
          )}
          <Button
            onClick={lancer}
            loading={detectionLoading}
            disabled={detectionLoading || exercices.length === 0}
          >
            <ScanSearch size={15} />
            Lancer la détection
          </Button>
        </>
      }
    >
      <section className="conv-section">
        <div className="conv-section__header">
          <span className="conv-section__icon">
            <ShieldAlert size={18} />
          </span>
          <div>
            <h2 className="conv-section__title">Méthodes selon la nature des données</h2>
            <p className="conv-section__subtitle">
              « Observation atypique » (1 méthode), « anomalie potentielle » (2
              méthodes), « valeur à vérifier » (3 méthodes ou plus) — aucune
              observation n&apos;est jamais qualifiée de fraude automatiquement.
            </p>
          </div>
        </div>
        <div
          style={{
            display: "flex",
            flexWrap: "wrap",
            gap: 8,
            marginTop: 12,
          }}
        >
          {referentiel?.methodes?.map((methode) => (
            <span key={methode.cle} className="badge" title={`Minimum ${methode.minimum_observations} observations`}>
              {methode.label}
            </span>
          ))}
        </div>
      </section>

      {detection && (
        <section className="conv-section">
          <div className="conv-section__header">
            <span className="conv-section__icon">
              <ScanSearch size={18} />
            </span>
            <div>
              <h2 className="conv-section__title">
                Résultat de la détection — exercice {detection.exercice}
              </h2>
              <p className="conv-section__subtitle">
                Calculé le {formatDateTime(detection.calcule_le)} ·{" "}
                {detection.total_observations} observations analysées ·{" "}
                {detection.total_detectees} signalées
              </p>
            </div>
            <button
              type="button"
              className="icon-btn"
              onClick={fermerDetection}
              aria-label="Fermer le résultat de la détection"
            >
              <X size={18} />
            </button>
          </div>

          <div className="dash-grid">
            <StatCard
              icon={Layers}
              label="Observations analysées"
              value={formatNumber(detection.total_observations)}
              sub={`exercice ${detection.exercice}`}
            />
            <StatCard
              icon={AlertTriangle}
              label="Observations signalées"
              value={formatNumber(detection.total_detectees)}
              sub="vérification humaine requise"
              variant="danger"
            />
            {(detection.synthese?.par_niveau?.valeur_a_verifier ?? 0) > 0 && (
              <StatCard
                icon={AlertTriangle}
                label="Valeurs à vérifier"
                value={formatNumber(detection.synthese.par_niveau.valeur_a_verifier)}
                sub="3 méthodes ou plus"
                variant="danger"
              />
            )}
            {(detection.synthese?.par_niveau?.anomalie_potentielle ?? 0) > 0 && (
              <StatCard
                icon={AlertTriangle}
                label="Anomalies potentielles"
                value={formatNumber(detection.synthese.par_niveau.anomalie_potentielle)}
                sub="2 méthodes"
                variant="warning"
              />
            )}
            {(detection.synthese?.par_niveau?.observation_atypique ?? 0) > 0 && (
              <StatCard
                icon={AlertTriangle}
                label="Observations atypiques"
                value={formatNumber(detection.synthese.par_niveau.observation_atypique)}
                sub="1 méthode"
                variant="info"
              />
            )}
          </div>

          {Object.keys(detection.variables_analysees || {}).length > 0 && (
            <div
              className="card card__padding"
              style={{ marginTop: 16 }}
            >
              <h3 className="chart-card__title">Variables analysées</h3>
              <div className="tableau tableau--scroll">
                <table className="tableau__table">
                  <thead>
                    <tr>
                      <th>Variable</th>
                      <th>Observations</th>
                      <th>Applicabilité</th>
                      <th>Signalées par méthode</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(detection.variables_analysees).map(
                      ([cle, variable]) => (
                        <tr key={cle}>
                          <td className="tableau__nom">{variable.label}</td>
                          <td className="tableau__montant">
                            {formatNumber(variable.observations)}
                          </td>
                          <td>
                            <Badge variant={variable.analysable ? "success" : "neutral"} dot>
                              {variable.analysable
                                ? "Analysée"
                                : variable.raison || "Non analysée"}
                            </Badge>
                          </td>
                          <td>
                            <span
                              style={{
                                display: "flex",
                                flexWrap: "wrap",
                                gap: 4,
                              }}
                            >
                              {Object.entries(variable.methodes || {}).map(
                                ([methode, rapport]) => (
                                  <Badge
                                    key={methode}
                                    variant={rapport.detectees > 0 ? "primary" : "neutral"}
                                  >
                                    {METHODE_LABELS[methode] || methode} : {formatNumber(rapport.detectees)}
                                  </Badge>
                                )
                              )}
                            </span>
                          </td>
                        </tr>
                      )
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </section>
      )}

      {detectionError && (
        <div className="card card__padding" style={{ marginBottom: 16 }}>
          <p className="field__error">{getApiErrorText(detectionError)}</p>
        </div>
      )}

      <section className="conv-section conv-section--filtres">
        <div className="conv-section__header">
          <span className="conv-section__icon">
            <Search size={18} />
          </span>
          <div>
            <h2 className="conv-section__title">Vérification des observations</h2>
            <p className="conv-section__subtitle">
              Observations signalées, comparaison des méthodes et workflow de
              vérification
            </p>
          </div>
        </div>

        <div className="filtres-bar">
          <div className="filtres-bar__champ filtres-bar__champ--recherche">
            <label className="field__label" htmlFor="recherche-anomalie">
              Recherche
            </label>
            <input
              id="recherche-anomalie"
              type="search"
              className="input"
              placeholder="N° de dossier, nom, matrice… justification…"
              value={filtres.recherche}
              onChange={(evenement) =>
                modifieFiltres({ recherche: evenement.target.value })
              }
            />
          </div>
          <div className="filtres-bar__champ">
            <Select
              label="Statut de vérification"
              value={filtres.statut_verification}
              onChange={(evenement) =>
                modifieFiltres({ statut_verification: evenement.target.value })
              }
              options={[
                { value: "", label: "Tous" },
                ...statutsOptions,
              ]}
            />
          </div>
          <div className="filtres-bar__champ">
            <Select
              label="Niveau"
              value={filtres.niveau}
              onChange={(evenement) =>
                modifieFiltres({ niveau: evenement.target.value })
              }
              options={[{ value: "", label: "Tous" }, ...niveauxOptions]}
            />
          </div>
          <div className="filtres-bar__champ">
            <Select
              label="Méthode"
              value={filtres.methode}
              onChange={(evenement) =>
                modifieFiltres({ methode: evenement.target.value })
              }
              options={[{ value: "", label: "Toutes" }, ...methodesOptions]}
            />
          </div>
          <div className="filtres-bar__champ">
            <Select
              label="Variable"
              value={filtres.variable}
              onChange={(evenement) =>
                modifieFiltres({ variable: evenement.target.value })
              }
              options={[{ value: "", label: "Toutes" }, ...variablesOptions]}
            />
          </div>
          <div className="filtres-bar__champ">
            <Select
              label="Trier par"
              value={filtres.tri}
              onChange={(evenement) =>
                modifieFiltres({ tri: evenement.target.value })
              }
              options={TRI_OPTIONS}
            />
          </div>
          <div className="filtres-bar__champ">
            <Select
              label="Ordre"
              value={filtres.ordre}
              onChange={(evenement) =>
                modifieFiltres({ ordre: evenement.target.value })
              }
              options={[
                { value: "desc", label: "Décroissant" },
                { value: "asc", label: "Croissant" },
              ]}
            />
          </div>
          {filtresActifs && (
            <button
              type="button"
              className="btn btn--ghost btn--md filtres-bar__reinitialiser"
              onClick={reinitialiserFiltres}
            >
              <RefreshCcw size={14} />
              Réinitialiser
            </button>
          )}
        </div>

        <AnomalieTable
          liste={liste}
          loading={loading}
          error={error}
          recharger={recharger}
          saut={saut}
          setSaut={setSaut}
          limite={limite}
          onOuvrir={setSelection}
          onLancerDetection={lancer}
        />
      </section>

      <AnomalieDetailModal
        anomalie={selection}
        onClose={() => setSelection(null)}
        canTraiter={canTraiter}
        onStatutChange={majSelection}
      />
    </PageContainer>
  );
}