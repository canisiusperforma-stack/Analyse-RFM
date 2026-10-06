import { Inbox } from "lucide-react";
import { cn } from "@/lib/utils";

export default function EmptyState({
  icon: Icon = Inbox,
  title = "Aucune donnée",
  description,
  action,
  className,
}) {
  return (
    <div className={cn("empty-state", className)}>
      <span className="empty-state__icon" aria-hidden="true">
        <Icon size={24} />
      </span>
      <h3 className="empty-state__title">{title}</h3>
      {description && (
        <p className="empty-state__description">{description}</p>
      )}
      {action && <div className="empty-state__action">{action}</div>}
    </div>
  );
}