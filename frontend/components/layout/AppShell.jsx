"use client";

import { usePathname } from "next/navigation";
import Sidebar from "@/components/layout/Sidebar";
import Header from "@/components/layout/Header";
import RequireAuth from "@/components/auth/RequireAuth";
import Forbidden from "@/components/auth/Forbidden";
import { usePermissions } from "@/hooks/usePermissions";
import { estRoutePublique, modulePourRoute } from "@/lib/permissions";

const AUTH_PATHS = ["/connexion"];

export default function AppShell({ children }) {
  const pathname = usePathname();
  const { ready, canAccessModule } = usePermissions();

  if (AUTH_PATHS.includes(pathname)) {
    return <div className="auth-shell">{children}</div>;
  }

  const module = modulePourRoute(pathname);
  const accesModele =
    !estRoutePublique(pathname) &&
    ready &&
    module &&
    !canAccessModule(module);

  const contenu = (
    <div className="app-shell">
      <Sidebar />
      <div className="app-main">
        <Header />
        <main className="app-content">
          {accesModele ? <Forbidden /> : children}
        </main>
      </div>
    </div>
  );

  if (estRoutePublique(pathname)) {
    return contenu;
  }

  return <RequireAuth>{contenu}</RequireAuth>;
}