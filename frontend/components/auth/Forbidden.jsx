import Link from "next/link";
import { LayoutDashboard, ShieldX } from "lucide-react";
import PageContainer from "@/components/layout/PageContainer";
import EmptyState from "@/components/ui/EmptyState";
import Badge from "@/components/ui/Badge";

export default function Forbidden({ message = "Accès non autorisé" }) {
  return (
    <PageContainer title="Accès refusé" subtitle="Permissions insuffisantes">
      <div className="card card--padding">
        <EmptyState
          icon={ShieldX}
          title={message}
          description="Votre rôle ne permet pas d'accéder à cette fonctionnalité. Si vous pensez qu'il s'agit d'une erreur, contactez un administrateur."
          action={
            <>
              <Badge variant="danger" dot>
                403 · Interdit
              </Badge>
              <Link href="/dashboard" className="btn btn--primary">
                <LayoutDashboard size={16} aria-hidden="true" />
                Retour au tableau de bord
              </Link>
            </>
          }
        />
      </div>
    </PageContainer>
  );
}