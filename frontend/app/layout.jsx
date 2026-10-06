import "./globals.css";
import Providers from "./providers";
import AppShell from "@/components/layout/AppShell";

export const metadata = {
  title: {
    default: "RFM SRB Vatovavy",
    template: "%s · RFM SRB Vatovavy",
  },
  description:
    "Plateforme intelligente d'analyse, de prévision et d'aide à la décision appliquée au remboursement des frais médicaux — Service Régional du Budget Vatovavy.",
};

export const viewport = {
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({ children }) {
  return (
    <html lang="fr">
      <body>
        <Providers>
          <AppShell>{children}</AppShell>
        </Providers>
      </body>
    </html>
  );
}