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

import { compactCurrency, formatCurrency, formatNumber } from "@/lib/formatters";

function avecCumul(evolution) {
  let cumul = 0;
  return (evolution || []).map((mois) => {
    cumul += Number(mois.montant_demande) || 0;
    return { ...mois, cumul };
  });
}

/**
 * Évolution mensuelle des dossiers déposés et des montants.
 *
 * Deux axes : le volume de dossiers à gauche, les montants à droite.
 * Le cumul demandé donne la pente de la consommation de l'exercice.
 */
export default function TemporalChart({
  evolution,
  titre = "Évolution mensuelle",
  sousTitre = "Demandes déposées, montants demandés et remboursés par mois",
  hauteur = 260,
}) {
  const donnees = avecCumul(evolution);
  if (donnees.length === 0) return null;

  return (
    <div className="card card__padding chart-card">
      <h3 className="chart-card__title">{titre}</h3>
      <p className="chart-card__subtitle">{sousTitre}</p>
      <div className="chart-card__body">
        <ResponsiveContainer width="100%" height={hauteur}>
          <ComposedChart data={donnees} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
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
            <Line
              yAxisId="montant"
              dataKey="cumul"
              name="Cumul demandé"
              stroke="#059669"
              strokeWidth={1.5}
              dot={false}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
