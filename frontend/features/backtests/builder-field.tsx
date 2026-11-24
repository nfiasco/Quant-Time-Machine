"use client";

import { Field, FieldDescription, FieldError, FieldLabel } from "@/components/ui/field";
import { cn } from "@/lib/utils";

/** What ties a control to its label and to the error or description under it. */
export type ControlProps = {
  id: string;
  "aria-invalid"?: true;
  "aria-describedby"?: string;
};

type BuilderFieldProps = {
  /** The control's id, which the label points at. */
  id: string;
  label: React.ReactNode;
  /**
   * Which row the field belongs to, for screen readers, such as "of filter 2": every row has
   * a field labelled "Signal", and forms mode reads the label alone.
   */
  labelContext?: string;
  /** Shown instead of the description while there is one. */
  error?: string;
  description?: React.ReactNode;
  /** Smaller text, for fields inside a signal or filter row. */
  compact?: boolean;
  className?: string;
  children: (control: ControlProps) => React.ReactNode;
};

/**
 * A labelled control for the builder (GUIDELINES.md §6): its error replaces its description
 * while there is one, and the control points at whichever is showing.
 */
export function BuilderField({
  id,
  label,
  labelContext,
  error,
  description,
  compact = false,
  className,
  children,
}: BuilderFieldProps) {
  const errorId = `${id}-error`;
  const descriptionId = `${id}-description`;
  return (
    <Field data-invalid={error ? true : undefined} className={className}>
      <FieldLabel htmlFor={id} className={cn(compact && "text-xs")}>
        {label}
        {labelContext ? <span className="sr-only">{` ${labelContext}`}</span> : null}
      </FieldLabel>
      {children({
        id,
        "aria-invalid": error ? true : undefined,
        "aria-describedby": error ? errorId : description ? descriptionId : undefined,
      })}
      {error ? (
        <FieldError id={errorId} className={cn(compact && "text-xs")}>
          {error}
        </FieldError>
      ) : description ? (
        <FieldDescription id={descriptionId} className={cn(compact && "text-xs")}>
          {description}
        </FieldDescription>
      ) : null}
    </Field>
  );
}

/**
 * An error for a whole section, such as a period with no decision, under its fields. Its
 * section carries `data-invalid-section`, so the form can move focus into it.
 */
export function SectionError({ id, error }: { id: string; error?: string }) {
  return error ? <FieldError id={id}>{error}</FieldError> : null;
}
