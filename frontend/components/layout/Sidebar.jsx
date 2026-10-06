"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { PanelLeftClose, PanelLeftOpen, ShieldCheck } from "lucide-react";
import { APP_VERSION, NAV_SECTIONS } from "@/lib/constants";
import { modulePourRoute } from "@/lib/permissions";
import { cn } from "@/lib/utils";
import { useApp } from "@/context/AppContext";
import { usePermissions } from "@/hooks/usePermissions";

export default function Sidebar() {
  const pathname = usePathname();
  const { sidebarCollapsed, toggleSidebar, mobileOpen, closeMobile } = useApp();
  const { canAccessModule } = usePermissions();

  const isActive = (href) =>
    pathname === href || pathname.startsWith(`${href}/`);

  const sections = NAV_SECTIONS.map((section) => ({
    ...section,
    items: section.items.filter((item) => {
      const module = modulePourRoute(item.href);
      return !module || canAccessModule(module);
    }),
  })).filter((section) => section.items.length > 0);

  return (
    <>
      {mobileOpen && (
        <div
          className="sidebar__overlay"
          onClick={closeMobile}
          aria-hidden="true"
        />
      )}
      <aside
        className={cn(
          "sidebar",
          sidebarCollapsed && "sidebar--collapsed",
          mobileOpen && "sidebar--open"
        )}
      >
        <div className="sidebar__header">
          <Link href="/" className="sidebar__brand" onClick={closeMobile}>
            <span className="brand-mark" aria-hidden="true">
              <ShieldCheck size={20} />
            </span>
            <span className="brand-text">
              <strong>RFM · SRB</strong>
              <small>Vatovavy</small>
            </span>
          </Link>
          <button
            type="button"
            className="icon-btn icon-btn--sidebar"
            onClick={toggleSidebar}
            aria-label={
              sidebarCollapsed ? "Agrandir le menu" : "Réduire le menu"
            }
          >
            {sidebarCollapsed ? (
              <PanelLeftOpen size={18} />
            ) : (
              <PanelLeftClose size={18} />
            )}
          </button>
        </div>

        <nav className="sidebar__nav" aria-label="Navigation principale">
          {sections.map((section) => (
            <div className="nav-section" key={section.title}>
              <span className="nav-section__title">{section.title}</span>
              <ul className="nav-section__list">
                {section.items.map((item) => (
                  <li key={item.href}>
                    <Link
                      href={item.href}
                      onClick={closeMobile}
                      className={cn(
                        "nav-link",
                        isActive(item.href) && "nav-link--active"
                      )}
                      title={item.label}
                    >
                      <item.icon size={18} className="nav-link__icon" />
                      <span className="nav-link__label">{item.label}</span>
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </nav>

        <div className="sidebar__footer">
          <span className="sidebar__version">Version {APP_VERSION}</span>
        </div>
      </aside>
    </>
  );
}