// The kinds of signal the builder offers, from GET /v1/catalog/signals (S8.5): each one's
// type, its description, and a field for each parameter, read from the parameter's JSON
// Schema. A signal added to the engine shows up here with no change to the frontend, as long
// as its parameters are numbers, choices, text, or true or false. Plain data, so the page
// can build it on the server and hand it to the form.

import type { Settled } from "@/lib/api/errors";
import type { CatalogSeries, SignalCatalog, V1Response } from "@/lib/api/types";

type FieldBase = {
  /** The parameter's name in the spec, such as "lookback_months". */
  name: string;
  /** Its label in sentence case, such as "Lookback months". */
  label: string;
  /** The schema's description on one line, or null. */
  description: string | null;
  /** False when the spec can leave it out: the API then uses its default. */
  required: boolean;
};

/** One parameter of a kind of signal, as the form edits it. */
export type ParamField =
  | (FieldBase & {
      kind: "integer" | "number";
      min: number | null;
      max: number | null;
      default: number | null;
    })
  | (FieldBase & { kind: "choice"; options: string[]; default: string | null })
  | (FieldBase & { kind: "text"; default: string | null })
  | (FieldBase & { kind: "boolean"; default: boolean | null })
  /** A value the spec must have but nobody chooses, such as `basis: "yoy_quarterly"`. */
  | (FieldBase & { kind: "fixed"; value: string | number | boolean });

export type SignalKind = {
  /** As a spec writes it, such as "momentum". */
  type: string;
  /** For people, such as "Revenue growth acceleration". */
  label: string;
  description: string;
  /** In the schema's order, without `type`. */
  fields: ParamField[];
};

export type SignalKinds = {
  kinds: SignalKind[];
  /** False when the catalog couldn't be loaded: signals can't be added or changed then. */
  loaded: boolean;
};

/** The builder's kinds of signal from the catalog's answer, or none if it failed. */
export function toSignalKinds(result: Settled<SignalCatalog>): SignalKinds {
  if (!result.ok) return { kinds: [], loaded: false };
  return { kinds: result.value.data.map(toSignalKind), loaded: true };
}

export function findKind(kinds: readonly SignalKind[], type: string): SignalKind | undefined {
  return kinds.find((kind) => kind.type === type);
}

/** A series a macro_change can follow, from GET /v1/catalog/series. */
export type SeriesChoice = { id: string; title: string };

/**
 * The series a macro_change can follow, in the catalog's order. None if the catalog
 * couldn't be loaded: the form then asks for the series' ID as text.
 */
export function toSeriesChoices(result: Settled<V1Response<CatalogSeries[]>>): SeriesChoice[] {
  if (!result.ok) return [];
  return result.value.data.map((series) => ({ id: series.series_id, title: series.title }));
}

/** The value a new signal starts with for a field the user chooses, or null. */
export function fieldDefault(field: ParamField): string | number | boolean | null {
  return field.kind === "fixed" ? field.value : field.default;
}

function toSignalKind({
  type,
  description,
  parameters,
}: SignalCatalog["data"][number]): SignalKind {
  const properties = isRecord(parameters.properties) ? parameters.properties : {};
  const required = Array.isArray(parameters.required) ? parameters.required : [];
  const fields: ParamField[] = [];
  for (const [name, schema] of Object.entries(properties)) {
    if (name === "type") continue; // the kind itself
    const field = toField(name, schema, required.includes(name));
    if (field) fields.push(field);
  }
  return {
    type,
    label: sentenceCase(type.replaceAll("_", " ")),
    description: oneLine(description),
    fields,
  };
}

/**
 * A parameter's field from its JSON Schema, as pydantic writes one: a `const`, an `enum` of
 * strings, or an integer, number, string, or boolean with optional `minimum`, `maximum`, and
 * `default`. Null for anything else, which the form leaves out (the API would say if it's
 * required).
 */
function toField(name: string, schema: unknown, required: boolean): ParamField | null {
  if (!isRecord(schema)) return null;
  const base: FieldBase = {
    name,
    label: sentenceCase(
      typeof schema.title === "string" ? schema.title : name.replaceAll("_", " "),
    ),
    description: typeof schema.description === "string" ? oneLine(schema.description) : null,
    required,
  };

  if (isScalar(schema.const)) return { ...base, kind: "fixed", value: schema.const };
  if (Array.isArray(schema.enum) && schema.enum.length > 0 && schema.enum.every(isString)) {
    return { ...base, kind: "choice", options: schema.enum, default: stringOrNull(schema.default) };
  }
  switch (schema.type) {
    case "integer":
    case "number":
      return {
        ...base,
        kind: schema.type,
        min: numberOrNull(schema.minimum),
        max: numberOrNull(schema.maximum),
        default: numberOrNull(schema.default),
      };
    case "string":
      return { ...base, kind: "text", default: stringOrNull(schema.default) };
    case "boolean":
      return {
        ...base,
        kind: "boolean",
        default: typeof schema.default === "boolean" ? schema.default : null,
      };
  }
  return null;
}

/** "Lookback Months" → "Lookback months". */
function sentenceCase(text: string): string {
  const lower = text.trim().toLowerCase();
  return lower.charAt(0).toUpperCase() + lower.slice(1);
}

/** The schema's docstrings keep their line breaks: "…12-1 by\ndefault." → "…12-1 by default." */
function oneLine(text: string): string {
  return text.replace(/\s+/g, " ").trim();
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isString(value: unknown): value is string {
  return typeof value === "string";
}

function isScalar(value: unknown): value is string | number | boolean {
  return typeof value === "string" || typeof value === "number" || typeof value === "boolean";
}

function stringOrNull(value: unknown): string | null {
  return typeof value === "string" ? value : null;
}

function numberOrNull(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}
