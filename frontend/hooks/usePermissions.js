"use client";

import { useMemo } from "react";
import { useAuth } from "@/context/AuthContext";
import {
  ROLE_LABELS,
  aLaPermission,
  aToutesLesPermissions,
  aUneDesPermissions,
  moduleAccessible,
  modulesAccessibles,
  permissionsEffectives,
} from "@/lib/permissions";

/**
 * Hook exposant les permissions de l'utilisateur courant.
 *
 * Retourne l'ensemble des permissions telles que fournies par le backend
 * (/auth/me, /auth/connexion). Le backend est la seule source d'autorité ;
 * ce hook ne sert qu'à masquer/afficher l'interface.
 */
export function usePermissions() {
  const { user, loading } = useAuth();

  const role = user?.role ?? null;
  const permissions = useMemo(
    () => permissionsEffectives(user),
    [user]
  );

  return useMemo(() => {
    const liste = (args) => (Array.isArray(args[0]) ? args[0].flat() : args);

    const has = (permission) => aLaPermission(permissions, permission);
    const hasAny = (...args) =>
      aUneDesPermissions(permissions, liste(args));
    const hasAll = (...args) =>
      aToutesLesPermissions(permissions, liste(args));
    const canAccessModule = (module) => moduleAccessible(permissions, module);

    return {
      role,
      roleLabel: role ? ROLE_LABELS[role] ?? role : null,
      isAdmin: role === "ADMIN",
      permissions,
      ready: !loading,
      has,
      can: has,
      hasAny,
      hasAll,
      canAccessModule,
      accessibleModules: () => modulesAccessibles(permissions),
    };
  }, [role, permissions, loading]);
}