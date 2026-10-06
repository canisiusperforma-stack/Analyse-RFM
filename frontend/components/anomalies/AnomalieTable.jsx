"use client";

import { AlertTriangle, Eye, RefreshCcw } from "lucide-react";

import Badge from "@/components/ui/Badge";
import EmptyState from "@/components/ui/EmptyState";
import Loading from "@/components/ui/Loading";
import { getApiErrorText } from "@/lib/errors";
import {
  METHODE_LABELS,
  NIVEAU_VARIANTS,
  STATUT_VARIANTS,
} from "@/lib/anomalies";
import {
  formatCurrency,
  formatNumber,
  formatScore,
} from "@/lib/formatters";

const VARIABLES_MONTANT = new Set([
  "montant_demande",
  "montant_accordee",
  "montant_paye",
]);

export function formaterValeurAlerte(anomalie) {
  const { variable, valeur } = anomalie;
  if (valeur == null) return "—";
  if (VARIABLES_MONTANT.has(variable)) return formatCurrency(valeur);
  if (variable === "delai_jours") return `${formatNumber(valeur)} j`;
  if (variable === "age_beneficiaire") {
    return `${formatNumber(Math.round(Number(valeur)))} ans`;
  }
  return formatNumber(valeur);
}

export default function AnomalieTable({
  liste,
  loading,
  error,
  recharger,
  saut,
  setSaut,
  limite,
  onOuvrir,
  onLancerDetection,
}) {
  const total = liste?.total ?? 0;
  const debut = total ? saut + 1 : 0;
  const fin = liste ? Math.min(saut + limite, total) : 0;

  if (loading && !liste) {
    return <Loading label="Chargement des observations signalées…" />;
  }

  if (error && !liste) {
    return (
      <div className="card card__padding">
        <EmptyState
          icon={AlertTriangle}
          title="Impossible de charger les observations"
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
    );
  }

  if (total === 0) {
    return (
      <div className="card card__padding">
        <EmptyState
          icon={AlertTriangle}
          title="Aucune observation signalée"
          description="Aucune observation atypique ne correspond aux filtres. Vous pouvez lancer une détection sur l'exercice sélectionné."
          action={
            <button
              type="button"
              className="btn btn--primary btn--md"
              onClick={onLancerDetection}
            >
              <AlertTriangle size={15} />
              Lancer la détection
            </button>
          }
        />
      </div>
    );
  }

  return (
    <div className="tableau tableau--scroll">
      <table className="tableau__table">
        <thead>
          <tr>
            <th>Observation</th>
            <th>Valeur</th>
            <th>Méthode(s)</th>
            <th>Score</th>
            <th>Niveau</th>
            <th>Justification</th>
            <th>Statut de vérification</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {liste.items.map((anomalie) => (
            <tr key={anomalie.id}>
              <td>
                <span className="tableau__code">{anomalie.numero_dossier}</span>
                <span className="tableau__nom">
                  {[anomalie.beneficiaire?.prenom, anomalie.beneficiaire?.nom]
                    .filter(Boolean)
                    .join(" ") || "—"}
                </span>
                <span className="tableau__sous-texte">
                  {anomalie.type_prestation || anomalie.statut_remboursement || ""}
                </span>
              </td>
              <td>
                <span className="tableau__nom">{anomalie.libelle_variable}</span>
                <span className="tableau__montant tableau__montant--execute">
                  {formaterValeurAlerte(anomalie)}
                </span>
              </td>
              <td>
                <div className="tableau__nom" style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
                  {anomalie.methodes_detectees?.map((methode) => (
                    <Badge key={methode} variant="primary">
                      {METHODE_LABELS[methode] || methode}
                    </Badge>
                  )) || "—"}
                </div>
              </td>
              <td className="tableau__montant">
                {formatScore(anomalie.score)}
              </td>
              <td>
                <Badge
                  variant={NIVEAU_VARIANTS[anomalie.niveau] || "neutral"}
                  dot
                >
                  {anomalie.label_niveau}
                </Badge>
                {anomalie.nombre_methodes > 1 && (
                  <span className="tableau__sous-texte">
                    {anomalie.nombre_methodes} méthodes
                  </span>
                )}
              </td>
              <td>
                <span
                  className="tableau__sous-texte"
                  style={{
                    maxWidth: 280,
                    whiteSpace: "nowrap",
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                    color: "var(--color-text-secondary)",
                  }}
                  title={anomalie.justification}
                >
                  {anomalie.justification}
                </span>
              </td>
              <td>
                <Badge
                  variant={
                    STATUT_VARIANTS[anomalie.statut_verification] || "neutral"
                  }
                  dot
                  title={anomalie.commentaire || undefined}
                >
                  {anomalie.label_statut_verification}
                </Badge>
              </td>
              <td>
                <button
                  type="button"
                  className="btn btn--ghost btn--sm"
                  onClick={() => onOuvrir(anomalie)}
                  aria-label={`Voir le détail de ${anomalie.numero_dossier}`}
                >
                  <Eye size={15} />
                  Détail
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <div className="tableau__pied">
        <span className="tableau__resume">
          {formatNumber(debut)}–{formatNumber(fin)} sur {formatNumber(total)}
        </span>
        <div className="tableau__nav">
          <button
            type="button"
            className="btn btn--ghost btn--sm"
            disabled={saut === 0 || loading}
            onClick={() => setSaut(Math.max(0, saut - limite))}
          >
            Précédent
          </button>
          <button
            type="button"
            className="btn btn--ghost btn--sm"
            disabled={fin >= total || loading}
            onClick={() => setSaut(saut + limite)}
          >
            Suivant
          </button>
        </div>
      </div>
    </div>
  );
}