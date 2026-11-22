// AI contribution: 50% or more AI-generated
/**
 * Rows for the Sources table (US-7.2, #319, #321).
 *
 * The provenance map comes from `GET /parameters`, already parsed by
 * parseParameterProvenance (US-7.1). Every parameter in it gets a row, and so
 * does every value the run used that the backend has no entry for, so a
 * missing source is shown instead of the input quietly disappearing.
 * `runValues` gives the "Used in this run" text for the run settings (#320).
 */
import {
  formatErrorMagnitude,
  formatSeconds,
  formatThreshold,
  strategyLabel,
} from "./run-settings";
import type { RunSettings } from "../types/runSettings";
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

/**
 * "Used in this run" text for an input every run uses but Run settings
 * cannot change, such as min_safe_gap. `/parameters` sends no values, so the
 * number itself cannot be shown yet.
 */
export const FIXED_VALUE = "Fixed value";

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

/** The disruption preset with its start and size, or "None" for a baseline run. */
function formatDisruption(settings: RunSettings): string {
  const preset = settings.disruption_preset ?? "none";
  if (preset === "none") return "None";
  const name = preset.replace("_", " ");
  return `${name[0].toUpperCase()}${name.slice(1)} at ${formatSeconds(settings.disruption_time_s ?? 120)}, `
    + formatSeconds(settings.disruption_magnitude ?? 60);
}

/** The run's settings as shown in Run settings, keyed by parameter name. */
export function runValues(settings: RunSettings): Record<string, string> {
  return {
    strategy: strategyLabel(settings.strategy),
    max_hold_time: formatSeconds(settings.max_hold_time),
    error_magnitude: formatErrorMagnitude(settings.error_magnitude),
    passenger_flow: settings.passenger_flow,
    disruption_enabled: formatDisruption(settings),
    // The API uses the error magnitude as kappa for every estimate (simulation_run.py).
    kappa: formatErrorMagnitude(settings.error_magnitude),
    // The threshold is only sent for Adaptive, so other runs did not use it.
    irregularity_threshold: settings.strategy === "adaptive"
      ? formatThreshold(settings.irregularity_threshold)
      : "Not used by this strategy",
  };
}
