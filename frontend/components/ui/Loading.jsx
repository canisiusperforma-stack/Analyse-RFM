import { Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

export default function Loading({
  variant = "card",
  label = "Chargement…",
  className,
}) {
  if (variant === "page") {
    return (
      <div className={cn("loading-page", className)} role="status" aria-live="polite">
        <Loader2 size={28} className="spinner" aria-hidden="true" />
        {label && <span>{label}</span>}
      </div>
    );
  }

  return (
    <div className={cn("loading-card", className)} role="status" aria-live="polite">
      <Loader2 size={20} className="spinner" aria-hidden="true" />
      {label && <span>{label}</span>}
    </div>
  );
}