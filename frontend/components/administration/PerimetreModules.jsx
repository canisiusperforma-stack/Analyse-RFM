"use client";

import { useMemo } from "react";
import Link from "next/link";
import { Check, Lock, SquareArrowOutUpRight } from "lucide-react";

import Badge from "@/components/ui/Badge";
import { MODULES } from "@/lib/permissions";
import { usePermissions } from "@/hooks/usePermissions";
import {
  couvertureParRole,
  descriptionModule,
  libelleModule,
  permissionsDuModule,
} from "@/lib/administration";

/**
 * Route d'accès à un module, lorsqu'il en possède une. Les modules sans page
 * propre (la matrice des habilitations n'a pas d'écran) sont simplement listés.
 */
const ROUTE_PAR_MODULE = {
  dashboard: "/dashboard",
  beneficiaires: "/beneficiaires",
  budget: "/budget",
  remboursements: "/remboursements",
  analyses: "/analyses",
  anomalies: "/analyses/anomalies",
  previsions: "/previsions",
  simulations: "/simulations",
  assistant: "/assistant-ia",
  documents: "/documents",
  rapports: "/rapports",
  utilisateurs: "/administration/utilisateurs",
  importation: "/imports",
};

/**
 * Périmètre fonctionnel de la plateforme.
 *
 * Elle liste les treize modules et, pour chacun, ce que le rôle de l'appelant
 * ouvre. Elle sert à deux choses : vérifier d'un coup d'œil qu'un module n'a pas
 * été restreint par erreur, et voir d'un coup d'œil *ceux que l'on ne voit pas*
 * — un module absent de la barre latérale ne se distingue pas, à l'écran, d'un
 * module qui n'existe pas.
 *
 * Elle est donc exhaustive, et affiche aussi l'inaccessible. Une carte ne
 * montrant que le visible donnerait à chaque agent la même lecture, et à
 * l'administrateur la fausse impression que la plateforme ne contient que ce que
 * son rôle autorise.
 */
export default function PerimetreModules() {
  const { role, canAccessModule } = usePermissions();

  const couvertures = useMemo(() => {
    const parRole = new Map(
      couvertureParRole().map((entree) => [entree.role, entree])
    );
    return MODULES.map((module) => ({
      module,
      accessible: canAccessModule(module),
      route: ROUTE_PAR_MODULE[module] ?? null,
      actions: permissionsDuModule(module).length,
      accordees: parRole.get(role)?.modules.includes(module) ?? false,
    }));
  }, [canAccessModule, role]);

  const accessibles = couvertures.filter((entree) => entree.accessible).length;

  return (
    <section className="card">
      <div className="card__header">
        <div>
          <h3 className="card__title">Périmètre de la plateforme</h3>
          <p className="text-muted">
            {accessibles} module(s) sur {MODULES.length} vous sont accessibles.
            Les autres existent — votre rôle ne les ouvre pas.
          </p>
        </div>
      </div>

      <div className="card__body">
        <ul className="admin-modules">
          {couvertures.map(({ module, accessible, route, actions, accordees }) => {
            const contenu = (
              <>
                <span className="admin-modules__entete">
                  <span className="admin-modules__nom">
                    {libelleModule(module)}
                  </span>
                  {accessible ? (
                    <Badge variant="success">
                      <Check size={12} aria-hidden="true" />
                      Accessible
                    </Badge>
                  ) : (
                    <Badge variant="neutral">
                      <Lock size={12} aria-hidden="true" />
                      Restreint
                    </Badge>
                  )}
                </span>
                <span className="admin-modules__description">
                  {descriptionModule(module)}
                </span>
                <span className="admin-modules__pied">
                  {actions} action(s) déclarée(s)
                  {accordees ? " · accordées à votre rôle" : ""}
                </span>
              </>
            );

            const classes = `admin-module${accessible ? "" : " est-restreint"}`;

            return (
              <li key={module} className={classes}>
                {route && accessible ? (
                  <Link href={route} className="admin-module__lien">
                    {contenu}
                    <SquareArrowOutUpRight
                      size={14}
                      aria-hidden="true"
                      className="admin-modules__lien-icone"
                    />
                  </Link>
                ) : (
                  <div className="admin-module__lien">{contenu}</div>
                )}
              </li>
            );
          })}
        </ul>
      </div>
    </section>
  );
}
