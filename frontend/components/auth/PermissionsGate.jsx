"use client";

import { usePermissions } from "@/hooks/usePermissions";

/**
 * Masque un contenu en fonction des permissions (affichage uniquement).
 *
 * Usage :
 *   <PermissionsGate permission="importation:importer">
 *     <ImportUpload />
 *   </PermissionsGate>
 *
 *   <PermissionsGate any={["rapports:generer", "rapports:exporter"]} fallback={null}>
 *     ...
 *   </PermissionsGate>
 *
 *   <PermissionsGate module="utilisateurs" fallback={null}>...</PermissionsGate>
 *
 * La sécurité est garantie par le backend ; ceci ne sert qu'à l'UX.
 */
export default function PermissionsGate({
  permission = null,
  any = [],
  all = [],
  module = null,
  fallback = null,
  children,
}) {
  const { ready, has, hasAny, hasAll, canAccessModule } = usePermissions();

  if (!ready) return fallback;

  let autorise = true;
  if (permission) autorise = has(permission);
  else if (any.length > 0) autorise = hasAny(any);
  else if (all.length > 0) autorise = hasAll(all);
  else if (module) autorise = canAccessModule(module);

  return autorise ? children : fallback;
}