import Link from "next/link";
import {
  BarChart3,
  Bot,
  Database,
  FileText,
  FlaskConical,
  Landmark,
  LineChart,
  Receipt,
  ShieldCheck,
  TrendingUp,
  Users,
} from "lucide-react";
import { APP_TAGLINE } from "@/lib/constants";
import Badge from "@/components/ui/Badge";

const FEATURES = [
  {
    icon: Users,
    title: "Bénéficiaires",
    description:
      "Analyse de la population bénéficiaire : fonctionnaires actifs et pensionnés, bénéficiaires du RFM.",
    href: "/beneficiaires",
  },
  {
    icon: Receipt,
    title: "Remboursements",
    description:
      "Suivi et analyse des demandes de remboursement des frais médicaux.",
    href: "/remboursements",
  },
  {
    icon: Landmark,
    title: "Budget et exécution",
    description:
      "Analyse du budget RFM et suivi de l'exécution budgétaire.",
    href: "/budget",
  },
  {
    icon: BarChart3,
    title: "Analyse statistique",
    description:
      "Statistiques descriptives et croisements de variables sur les données du SRB.",
    href: "/analyses/statistiques",
  },
  {
    icon: TrendingUp,
    title: "Analyse temporelle",
    description:
      "Évolution de la consommation dans le temps : mensuelle, trimestrielle, annuelle.",
    href: "/analyses/temporelle",
  },
  {
    icon: LineChart,
    title: "Prévision de consommation",
    description:
      "Prévision de la consommation budgétaire pour éclairer les décisions.",
    href: "/previsions",
  },
  {
    icon: FlaskConical,
    title: "Simulation budgétaire",
    description:
      "Construction de scénarios et évaluation de leur impact budgétaire.",
    href: "/simulations",
  },
  {
    icon: Bot,
    title: "Assistant IA",
    description:
      "Assistant analytique et recherche documentaire (RAG) fondée sur les documents autorisés.",
    href: "/assistant-ia",
  },
  {
    icon: FileText,
    title: "Rapports",
    description:
      "Génération de rapports PDF et Excel réutilisables.",
    href: "/rapports",
  },
  {
    icon: Database,
    title: "Importation de données",
    description:
      "Import de fichiers CSV/Excel avec validation, normalisation, contrôle des doublons et rapport d'importation.",
    href: "/imports",
  },
];

export default function Accueil() {
  return (
    <div className="page-container">
      <section className="hero">
        <Badge variant="primary" dot>
          Plateforme institutionnelle · SRB Vatovavy
        </Badge>
        <h1 className="hero__title">
          Analyse, prévision et aide à la décision pour le{" "}
          <span>remboursement des frais médicaux</span>
        </h1>
        <p className="hero__subtitle">
          {APP_TAGLINE}. La plateforme centralise l'analyse de la population
          bénéficiaire, l'exécution budgétaire et les demandes de remboursement,
          et appuie les décisions du Service Régional du Budget Vatovavy.
        </p>
        <div className="hero__actions">
          <Link href="/dashboard" className="btn btn--primary btn--lg">
            Accéder au tableau de bord
          </Link>
          <Link href="/analyses" className="btn btn--secondary btn--lg">
            Explorer les analyses
          </Link>
        </div>
      </section>

      <section className="features-section">
        <h2>Capacités de la plateforme</h2>
        <p>Les principaux modules disponibles au sein de l'application.</p>
        <div className="features-grid">
          {FEATURES.map((feature) => (
            <Link
              key={feature.title}
              href={feature.href}
              className="feature-card"
            >
              <span className="feature-card__icon" aria-hidden="true">
                <feature.icon size={22} />
              </span>
              <span className="feature-card__title">{feature.title}</span>
              <span className="feature-card__text">{feature.description}</span>
            </Link>
          ))}
        </div>
      </section>

      <section className="home-note">
        <p className="home-note__title">
          <ShieldCheck size={16} /> Confidentialité et intégrité des données
        </p>
        <p>
          Toutes les données transitent exclusivement par l'API sécurisée de la
          plateforme ; les valeurs financières du SRB ne sont jamais publiées
          sans validation. Les éventuelles données de démonstration sont
          clairement identifiées comme fictives, et une observation atypique
          n'est jamais considérée comme une fraude : elle est signalée comme
          « anomalie potentielle » ou « valeur à vérifier ».
        </p>
      </section>
    </div>
  );
}