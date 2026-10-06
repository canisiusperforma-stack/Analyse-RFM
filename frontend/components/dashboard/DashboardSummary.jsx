import Badge from "@/components/ui/Badge";
import { AlertTriangle, CheckCircle, Info, TrendingUp } from "lucide-react";

const ICONES = {
  positif: CheckCircle,
  avertissement: AlertTriangle,
  critique: AlertTriangle,
  informations: Info,
};

const NIVEAUX = {
  positif: "success",
  avertissement: "warning",
  critique: "danger",
  informations: "info",
};

export default function DashboardSummary({ evenements = [] }) {
  if (!evenements.length) return null;

  return (
    <section className="dash-section">
      <h2 className="dash-section__title">
        <TrendingUp size={18} />
        Résumé analytique
      </h2>
      <ul className="summary-list">
        {evenements.map((evenement) => {
          const Icon = ICONES[evenement.niveau] || Info;
          return (
            <li
              key={evenement.cle}
              className={`summary-item summary-item--${evenement.niveau}`}
            >
              <span className="summary-item__icon">
                <Icon size={16} />
              </span>
              <p className="summary-item__message">{evenement.message}</p>
              <Badge variant={NIVEAUX[evenement.niveau] || "info"}>
                {evenement.niveau}
              </Badge>
            </li>
          );
        })}
      </ul>
    </section>
  );
}