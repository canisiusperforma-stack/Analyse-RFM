import PageContainer from "@/components/layout/PageContainer";
import EmptyState from "@/components/ui/EmptyState";
import Badge from "@/components/ui/Badge";
import { Construction } from "lucide-react";

export default function PagePlaceholder({
  title,
  subtitle,
  description,
  icon: Icon = Construction,
  capabilities = [],
}) {
  return (
    <PageContainer title={title} subtitle={subtitle}>
      <div className="card card--padding">
        <EmptyState
          icon={Icon}
          title={title}
          description={
            description ||
            "Ce module sera disponible prochainement dans la plateforme."
          }
          action={<Badge variant="warning" dot>Module en cours de développement</Badge>}
        />
        {capabilities.length > 0 && (
          <div className="placeholder-capabilities">
            <h4>Fonctionnalités prévues</h4>
            <ul className="placeholder-list">
              {capabilities.map((capability) => (
                <li key={capability}>{capability}</li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </PageContainer>
  );
}