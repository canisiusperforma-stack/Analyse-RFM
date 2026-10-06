import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { formatNumber, formatPercent } from "@/lib/formatters";

/**
 * Histogramme d'une variable quantitative en classes d'effectifs égaux.
 *
 * `classes` suit la forme renvoyée par le backend : chaque entrée porte
 * l'intervalle, l'effectif et la part que représente la classe. L'axe des
 * ordonnées porte donc des effectifs, pas des montants : les bornes de
 * classes sont des montants et sont indiquées sur l'axe des abscisses.
 */
export default function StatisticalChart({
  classes,
  titre,
  sousTitre = "Répartition en 5 classes d'effectifs égaux",
  couleur = "#2563eb",
  hauteur = 240,
}) {
  if (!classes || classes.length === 0) return null;

  const donnees = classes.map((classe) => ({
    intervalle: classe.intervalle,
    effectif: classe.effectif,
    pourcentage: classe.pourcentage,
  }));

  return (
    <div className="card card__padding chart-card">
      <h3 className="chart-card__title">{titre}</h3>
      <p className="chart-card__subtitle">{sousTitre}</p>
      <div className="chart-card__body">
        <ResponsiveContainer width="100%" height={hauteur}>
          <BarChart data={donnees} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
            <XAxis dataKey="intervalle" tick={{ fontSize: 10 }} interval={0} />
            <YAxis tick={{ fontSize: 11 }} width={36} allowDecimals={false} />
            <Tooltip
              formatter={(valeur, nom, item) =>
                nom === "effectif"
                  ? [
                      `${formatNumber(valeur)} (${formatPercent(item.payload.pourcentage)})`,
                      "Dossiers",
                    ]
                  : [formatNumber(valeur), nom]
              }
            />
            <Bar dataKey="effectif" name="effectif" radius={[4, 4, 0, 0]}>
              {donnees.map((classe) => (
                <Cell
                  key={classe.intervalle}
                  fill={couleur}
                  fillOpacity={classe.effectif === 0 ? 0.35 : 1}
                />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
