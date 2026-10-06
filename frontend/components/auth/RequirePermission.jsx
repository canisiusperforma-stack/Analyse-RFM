"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { usePermissions } from "@/hooks/usePermissions";
import { useAuth } from "@/context/AuthContext";
import Loading from "@/components/ui/Loading";

/**
 * Garde de page : redirige vers `/403` si l'utilisateur n'a pas le droit.
 *
 * Usage :
 *   <RequirePermission permission="rapports:generer">
 *     <PageRapports />
 *   </RequirePermission>
 *   <RequirePermission module="utilisateurs">...</RequirePermission>
 *
 * Le backend reste l'autorité ; cette garde ne fait que l'UX.
 */
export default function RequirePermission({
  permission = null,
  any = [],
  all = [],
  module = null,
  redirectTo = "/403",
  children,
}) {
  const { loading, isAuthenticated } = useAuth();
  const { ready, has, hasAny, hasAll, canAccessModule } = usePermissions();
  const router = useRouter();

  let autorise = true;
  if (ready && !loading && isAuthenticated) {
    if (permission) autorise = has(permission);
    else if (any.length > 0) autorise = hasAny(any);
    else if (all.length > 0) autorise = hasAll(all);
    else if (module) autorise = canAccessModule(module);
  }

  useEffect(() => {
    if (loading) return;
    if (!isAuthenticated) return;
    if (ready && !autorise) {
      router.replace(redirectTo);
    }
  }, [loading, isAuthenticated, ready, autorise, redirectTo, router]);

  if (loading || !ready) {
    return <Loading variant="page" label="Vérification des droits…" />;
  }

  if (!autorise) return null;

  return children;
}