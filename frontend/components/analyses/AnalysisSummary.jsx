import { AlertTriangle, CheckCircle, Info, Lightbulb } from "lucide-react";

import Badge from "@/components/ui/Badge";
import {
  formatCurrency,
  formatNumber,
  formatPercent,
} from "@/lib/formatters";

const ICONES = {
  positif: CheckCircle,
  avertissement: AlertTriangle,
  critique: AlertTriangle,
  informations: Info,
};

const VARIANTS = {
  positif: "success",
  avertissement: "warning",
  critique: "danger",
  informations: "info",
};

function ratio(numerateur, denominateur) {
  const n = Number(numerateur);
  const d = Number(denominateur);
  if (!Number.isFinite(n) || !Number.isFinite(d) || d === 0) return null;
  return n / d;
}

function libelleVariable(variables, cle) {
  return variables?.[cle] || cle;
}

/**
 * Constats établis **uniquement** à partir des indicateurs déjà calculés par
 * le backend : aucun chiffre n'est estimé, aucun texte n'est généré par un
 * modèle. Chaque point est un fait vérifiable sur les pages Statistiques et
 * Évolution temporelle.
 */
function pointsDeLecture(temporelle, statistiques) {
  const synthese = temporelle?.synthese;
  if (!synthese) return [];

  const comparaison = temporelle.comparaison;
  const evolution = temporelle.evolution || [];
  const points = [];

  const moisActifs = evolution.filter((mois) => mois.demandes > 0);
  if (moisActifs.length > 0) {
    const plusCharge = moisActifs.reduce((a, b) =>
      b.montant_demande > a.montant_demande ? b : a
    );
    const part = ratio(plusCharge.montant_demande, synthese.montant_demande);
    points.push({
      cle: "concentration",
      niveau: part != null && part >= 0.2 ? "avertissement" : "informations",
      message:
        `${plusCharge.libelle} porte le montant demandé le plus élevé de l'exercice ` +
        `(${formatCurrency(plusCharge.montant_demande)}` +
        (part != null ? `, soit ${formatPercent(part)} du total` : "") +
        `), sur ${formatNumber(moisActifs.length)} mois d'activité.`,
    });
  }

  if (synthese.taux_execution != null) {
    const taux = synthese.taux_execution;
    const ecart = comparaison?.taux_execution?.ecart;
    const precision =
      ecart != null
        ? `, en ${ecart >= 0 ? "hausse" : "baisse"} de ${formatPercent(Math.abs(ecart))} par rapport à l'exercice ${comparaison.exercice_precedent}`
        : "";
    points.push({
      cle: "execution",
      niveau: taux >= 0.8 ? "positif" : taux >= 0.5 ? "avertissement" : "critique",
      message: `Le taux d'exécution atteint ${formatPercent(taux)}${precision}.`,
    });
  }

  const demande = statistiques?.descriptives?.montant_demande;
  const coefficientVariation = ratio(demande?.ecart_type, demande?.moyenne);
  if (coefficientVariation != null) {
    points.push({
      cle: "dispersion",
      niveau:
        coefficientVariation >= 1
          ? "avertissement"
          : coefficientVariation >= 0.6
            ? "informations"
            : "positif",
      message:
        `Les montants demandés ont un coefficient de variation de ` +
        `${formatPercent(coefficientVariation)} (écart-type ${formatCurrency(demande.ecart_type)} ` +
        `pour une moyenne de ${formatCurrency(demande.moyenne)}) : ` +
        `${coefficientVariation >= 1 ? "la consommation est portée par une minorité de dossiers" : "les dossiers sont de taille comparable"}.`,
    });
  }

  const asymetrie = ratio(
    (demande?.moyenne ?? 0) - (demande?.mediane ?? 0),
    demande?.mediane
  );
  if (asymetrie != null && Math.abs(asymetrie) >= 0.2) {
    points.push({
      cle: "asymetrie",
      niveau: asymetrie > 0 ? "avertissement" : "informations",
      message:
        `La moyenne des montants demandés (${formatCurrency(demande.moyenne)}) est ` +
        `${asymetrie > 0 ? "nettement supérieure" : "nettement inférieure"} à la médiane ` +
        `(${formatCurrency(demande.mediane)}) : la distribution n'est pas symétrique.`,
    });
  }

  const delai = statistiques?.descriptives?.delai_jours;
  if (delai?.mediane != null) {
    points.push({
      cle: "delai",
      niveau:
        delai.mediane > 90 ? "avertissement" : delai.mediane > 45 ? "informations" : "positif",
      message:
        `Le délai médian de traitement est de ${formatNumber(delai.mediane)} jours ` +
        `pour une moyenne de ${formatNumber(delai.moyenne)} jours ` +
        `(minimum ${formatNumber(delai.minimum)}, maximum ${formatNumber(delai.maximum)}).`,
    });
  }

  const correlation = statistiques?.correlations?.pertinentes?.[0];
  if (correlation) {
    const variables = statistiques.variables;
    points.push({
      cle: "correlation",
      niveau: "informations",
      message:
        `La relation linéaire la plus marquée associe ` +
        `${libelleVariable(variables, correlation.a)} et ${libelleVariable(variables, correlation.b)} ` +
        `(r = ${formatNumber(correlation.correlation.toFixed(2))}, intensité ${correlation.intensite}).`,
    });
  }

  const population = statistiques?.actifs_pensionnes?.effectifs_population;
  const effectif = (population?.actif ?? 0) + (population?.pensionne ?? 0);
  const partPensionnes = ratio(population?.pensionne, effectif);
  if (effectif > 0) {
    points.push({
      cle: "population",
      niveau: "informations",
      message:
        `La population recense ${formatNumber(effectif)} bénéficiaires ` +
        `(${formatNumber(population.actif)} actifs, ${formatNumber(population.pensionne)} pensionnés` +
        (partPensionnes != null
          ? `, soit ${formatPercent(partPensionnes)} de l'effectif`
          : "") +
        `).`,
    });
  }

  return points;
}

/**
 * Lecture narrative d'un exercice : constats déterministes calculés à partir
 * de l'analyse temporelle et des statistiques descriptives.
 */
export default function AnalysisSummary({ temporelle, statistiques }) {
  const points = pointsDeLecture(temporelle, statistiques);
  if (points.length === 0) return null;

  return (
    <section className="dash-section">
      <div className="dash-section__header">
        <span className="dash-section__icon" aria-hidden="true">
          <Lightbulb size={18} />
        </span>
        <div>
          <h2 className="dash-section__title">Lecture de l'exercice</h2>
          <p className="dash-section__subtitle">
            Constats établis par le code à partir des indicateurs déjà calculés
          </p>
        </div>
      </div>
      <ul className="summary-list">
        {points.map((point) => {
          const Icon = ICONES[point.niveau] || Info;
          return (
            <li
              key={point.cle}
              className={`summary-item summary-item--${point.niveau}`}
            >
              <span className="summary-item__icon" aria-hidden="true">
                <Icon size={16} />
              </span>
              <p className="summary-item__message">{point.message}</p>
              <Badge variant={VARIANTS[point.niveau] || "info"}>
                {point.niveau}
              </Badge>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
