"use client";

import { useId } from "react";
import { cn } from "@/lib/utils";

export default function Select({
  label,
  error,
  hint,
  required = false,
  options = [],
  placeholder = "Sélectionner…",
  className,
  children,
  id,
  ...props
}) {
  const autoId = useId();
  const selectId = id || autoId;

  return (
    <div className={cn("field", className)}>
      {label && (
        <label className="field__label" htmlFor={selectId}>
          {label}
          {required && (
            <span className="field__required" aria-hidden="true">
              {" "}
              *
            </span>
          )}
        </label>
      )}
      <select
        id={selectId}
        className={cn("select", error && "input--error")}
        aria-invalid={Boolean(error)}
        {...props}
      >
        {!props.value && (
          <option value="" disabled>
            {placeholder}
          </option>
        )}
        {children
          ? children
          : options.map((option) =>
              typeof option === "string" ? (
                <option key={option} value={option}>
                  {option}
                </option>
              ) : (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              )
            )}
      </select>
      {hint && !error && <span className="field__hint">{hint}</span>}
      {error && <span className="field__error">{error}</span>}
    </div>
  );
}