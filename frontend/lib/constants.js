import {
  LayoutDashboard,
  Users,
  Receipt,
  Landmark,
  BarChart3,
  Calculator,
  TrendingUp,
  AlertTriangle,
  LineChart,
  FlaskConical,
  FolderOpen,
  Bot,
  FileText,
  ShieldCheck,
  UserCog,
  Database,
} from "lucide-react";

export const APP_NAME = "RFM SRB Vatovavy";
export const APP_TAGLINE =
  "Plateforme intelligente d'analyse, de prévision et d'aide à la décision";
export const APP_VERSION = "1.0.0";

export const NAV_SECTIONS = [
  {
    title: "Pilotage",
    items: [
      { label: "Tableau de bord", href: "/dashboard", icon: LayoutDashboard },
    ],
  },
  {
    title: "Gestion",
    items: [
      { label: "Bénéficiaires", href: "/beneficiaires", icon: Users },
      { label: "Remboursements", href: "/remboursements", icon: Receipt },
      { label: "Budget RFM", href: "/budget", icon: Landmark },
    ],
  },
  {
    title: "Analyse et décision",
    items: [
      { label: "Analyses", href: "/analyses", icon: BarChart3 },
      { label: "Statistiques", href: "/analyses/statistiques", icon: Calculator },
      {
        label: "Évolution temporelle",
        href: "/analyses/temporelle",
        icon: TrendingUp,
      },
      {
        label: "Détection d'anomalies",
        href: "/analyses/anomalies",
        icon: AlertTriangle,
      },
      { label: "Prévisions", href: "/previsions", icon: LineChart },
      { label: "Simulations", href: "/simulations", icon: FlaskConical },
    ],
  },
  {
    title: "Documents et IA",
    items: [
      { label: "Documents", href: "/documents", icon: FolderOpen },
      { label: "Assistant IA", href: "/assistant-ia", icon: Bot },
    ],
  },
  {
    title: "Production",
    items: [
      {
        label: "Importation de données",
        href: "/imports",
        icon: Database,
      },
      { label: "Rapports", href: "/rapports", icon: FileText },
      {
        label: "Administration",
        href: "/administration",
        icon: ShieldCheck,
      },
      {
        label: "Utilisateurs",
        href: "/administration/utilisateurs",
        icon: UserCog,
      },
    ],
  },
];

const ALL_NAV_ITEMS = NAV_SECTIONS.flatMap((s) => s.items).sort(
  (a, b) => b.href.length - a.href.length
);

export function findNavByPath(pathname) {
  return ALL_NAV_ITEMS.find(
    (item) => pathname === item.href || pathname.startsWith(item.href + "/")
  );
}