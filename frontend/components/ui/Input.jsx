"use client";

import { useId } from "react";
import { cn } from "@/lib/utils";

export default function Input({
  label,
  error,
  hint,
  required = false,
  className,
  id,
  ...props
}) {
  const autoId = useId();
  const inputId = id || autoId;

  return (
    <div className={cn("field", className)}>
      {label && (
        <label className="field__label" htmlFor={inputId}>
          {label}
          {required && (
            <span className="field__required" aria-hidden="true">
              {" "}
              *
            </span>
          )}
        </label>
      )}
      <input
        id={inputId}
        className={cn("input", error && "input--error")}
        aria-invalid={Boolean(error)}
        {...props}
      />
      {hint && !error && <span className="field__hint">{hint}</span>}
      {error && <span className="field__error">{error}</span>}
    </div>
  );
}