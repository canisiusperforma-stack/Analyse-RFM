"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { LogIn, LogOut, Menu } from "lucide-react";
import { findNavByPath } from "@/lib/constants";
import { ROLE_LABELS } from "@/lib/permissions";
import { useApp } from "@/context/AppContext";
import { useAuth } from "@/context/AuthContext";
import { initials } from "@/lib/formatters";
import Button from "@/components/ui/Button";

function renderUserName(user) {
  if (user?.prenom && user?.nom) return `${user.prenom} ${user.nom}`;
  return user?.prenom || user?.nom || user?.email || "Utilisateur";
}

function UserZone() {
  const { user, isAuthenticated, logout } = useAuth();
  const router = useRouter();

  const handleLogout = () => {
    logout();
    router.replace("/connexion");
  };

  if (isAuthenticated && user) {
    return (
      <div className="header__user">
        <span className="avatar" aria-hidden="true">
          {initials(renderUserName(user))}
        </span>
        <div className="header__user-info">
          <strong title={renderUserName(user)}>{renderUserName(user)}</strong>
          <small>{user?.role ? ROLE_LABELS[user.role] ?? user.role : "Utilisateur"}</small>
        </div>
        <Button
          variant="ghost"
          onClick={handleLogout}
          size="sm"
          aria-label="Se déconnecter"
          title="Se déconnecter"
        >
          <LogOut size={16} />
        </Button>
      </div>
    );
  }

  return (
    <Button variant="primary" size="sm" render={<Link href="/connexion" />}>
      <LogIn size={16} />
      <span>Se connecter</span>
    </Button>
  );
}

export default function Header() {
  const pathname = usePathname();
  const { toggleMobile } = useApp();
  const navItem = findNavByPath(pathname);
  const title = navItem?.label || (pathname === "/" ? "Accueil" : "Accueil");

  return (
    <header className="header">
      <button
        type="button"
        className="icon-btn header__hamburger"
        onClick={toggleMobile}
        aria-label="Ouvrir le menu"
      >
        <Menu size={20} />
      </button>
      <h2 className="header__title">{title}</h2>
      <div className="header__actions">
        <UserZone />
      </div>
    </header>
  );
}