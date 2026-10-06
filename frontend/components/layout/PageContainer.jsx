import { cn } from "@/lib/utils";

export default function PageContainer({
  title,
  subtitle,
  actions,
  children,
  className,
}) {
  return (
    <div className={cn("page-container", className)}>
      {(title || actions) && (
        <div className="page-header">
          <div>
            {title && <h1 className="page-header__title">{title}</h1>}
            {subtitle && <p className="page-header__subtitle">{subtitle}</p>}
          </div>
          {actions && <div className="page-header__actions">{actions}</div>}
        </div>
      )}
      {children}
    </div>
  );
}