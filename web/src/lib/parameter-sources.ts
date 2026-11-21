// AI contribution: 50% or more AI-generated
/**
 * Rows for the Sources table (US-7.2, #319, #321).
 *
 * The provenance map comes from `GET /parameters`, already parsed by
 * parseParameterProvenance (US-7.1). Every parameter in it gets a row, and so
 * does every value the run used that the backend has no entry for, so a
 * missing source is shown instead of the input quietly disappearing.
 */
import {
  normalizeClassification,
  type ConfidenceClassification,
  type ParameterProvenanceMap,
} from "../types/provenance";

/** What each label means, worded as on the Sources mockup (Mockups wiki page). */
export const CLASSIFICATION_MEANINGS: Record<ConfidenceClassification, string> = {
  measured: "Counted or timed by the team at the station.",
  estimated: "Worked out from related data.",
  published: "Taken from STM or REM data, such as GTFS schedules.",
  assumed: "A modelling choice waiting on stakeholder confirmation.",
};

/** One row of the Sources table; null fields mean nothing is recorded. */
export interface SourceRow {
  name: string;
  label: string;
  value: string | null;
  classification: ConfidenceClassification | null;
  sourceName: string | null;
  sourceLink: string | null;
}

// Names for the run settings; other inputs show their backend key.
const LABELS: Readonly<Record<string, string>> = {
  strategy: "Strategy",
  max_hold_time: "Maximum hold",
  irregularity_threshold: "Irregularity threshold",
  error_magnitude: "Prediction error magnitude",
  passenger_flow: "Passenger flow",
  disruption_enabled: "Demo disruption",
};

/**
 * One row per parameter with provenance, then one per value without it.
 * `values` holds what the current run used, keyed by parameter name.
 */
export function buildSourceRows(
  provenance: Readonly<ParameterProvenanceMap>,
  values: Readonly<Record<string, string>> = {},
): SourceRow[] {
  const extra = Object.keys(values).filter((name) => !(name in provenance));
  return [...Object.keys(provenance), ...extra].map((name) => {
    const entry = provenance[name];
    return {
      name,
      label: LABELS[name] ?? name,
      value: values[name] ?? null,
      classification: normalizeClassification(entry?.classification),
      sourceName: entry?.source_name?.trim() || null,
      sourceLink: entry?.source_link ?? null,
    };
  });
}
