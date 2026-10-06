import { cloneElement } from "react";
import { Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

const SIZES = {
  sm: "btn--sm",
  md: "btn--md",
  lg: "btn--lg",
};

const VARIANTS = {
  primary: "btn--primary",
  secondary: "btn--secondary",
  outline: "btn--outline",
  ghost: "btn--ghost",
  danger: "btn--danger",
};

export default function Button({
  variant = "primary",
  size = "md",
  loading = false,
  fullWidth = false,
  className,
  disabled,
  children,
  type,
  render,
  ...props
}) {
  const classes = cn(
    "btn",
    VARIANTS[variant],
    SIZES[size],
    fullWidth && "btn--block",
    className
  );

  if (render) {
    return cloneElement(render, {
      className: cn(render.props.className, classes),
      "aria-disabled": disabled || loading || undefined,
      ...props,
    });
  }

  return (
    <button
      type={type}
      disabled={disabled || loading}
      className={classes}
      {...props}
    >
      {loading && (
        <Loader2
          size={16}
          className="btn__spinner"
          aria-hidden="true"
          data-testid="button-spinner"
        />
      )}
      {children}
    </button>
  );
}