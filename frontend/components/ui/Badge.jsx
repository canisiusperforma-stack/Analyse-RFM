import { cn } from "@/lib/utils";

const VARIANTS = {
  neutral: "badge--neutral",
  primary: "badge--primary",
  success: "badge--success",
  warning: "badge--warning",
  danger: "badge--danger",
  info: "badge--info",
};

export default function Badge({
  variant = "neutral",
  dot = false,
  className,
  children,
  ...props
}) {
  return (
    <span
      className={cn("badge", VARIANTS[variant], className)}
      role={props.title ? undefined : "status"}
      {...props}
    >
      {dot && <span className="badge__dot" aria-hidden="true" />}
      {children}
    </span>
  );
}