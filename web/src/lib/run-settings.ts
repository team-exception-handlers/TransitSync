// AI contribution: 50% or more AI-generated
/**
 * Single source of truth for the run settings panel: the strategy list, each
 * control's range, the backend defaults, and the request body builder.
 *
 * The limits copy api/simulation_run.py (SimulationRunRequest). Keeping them
 * here, next to the builder, means the sliders, the store and the request can
 * never disagree about what the API accepts.
 */
import type { RunRequestBody, RunSettings, StrategyName } from "../types/runSettings";

/** One strategy as shown on a radio card. */
export interface StrategyOption {
  name: StrategyName;
  label: string;
  description: string;
}

// Order follows the Scenario setup mockup. "Coordinated" is the mockup's name
// for the backend's rolling_horizon strategy.
export const STRATEGY_OPTIONS: readonly StrategyOption[] = [
  { name: "no_control", label: "No control",
    description: "Trains always leave on schedule. The baseline." },
  { name: "schedule_based", label: "Schedule-based holding",
    description: "Hold only trains running early." },
  { name: "headway_regulation", label: "Headway regulation",
    description: "Hold to keep even gaps between trains." },
  { name: "connection_protection", label: "Connection protection",
    description: "Hold when time saved for transfers beats time lost, up to the maximum." },
  { name: "rolling_horizon", label: "Coordinated",
    description: "Plans holds ahead over the upcoming stops instead of one train at a time." },
  { name: "adaptive", label: "Adaptive",
    description: "Protects connections, and switches to headway regulation when service is too irregular." },
];

/** Inclusive slider range; values are kept on multiples of `step`. */
export interface SettingRange {
  min: number;
  max: number;
  step: number;
}

// The API requires 0 < max_hold_time <= 300 in multiples of 5, so 5 is the
// smallest value a user can pick.
export const MAX_HOLD_RANGE: SettingRange = { min: 5, max: 300, step: 5 };

// The API only requires threshold >= 0. The upper end is a UI choice: a mean
// deviation of 1 means gaps are off by a whole headway on average.
export const THRESHOLD_RANGE: SettingRange = { min: 0, max: 1, step: 0.05 };

/** Backend defaults, plus the panel's starting threshold for Adaptive. */
export const DEFAULT_RUN_SETTINGS: RunSettings = {
  strategy: "no_control",
  max_hold_time: 300,
  irregularity_threshold: 0.25,
};

/**
 * Bring `value` into `range` and onto the nearest step, so the store never
 * holds a number the API would reject. A non-finite value (NaN from an empty
 * input) returns `fallback`, the value the control already had.
 */
export function snapToRange(value: number, range: SettingRange, fallback: number): number {
  if (!Number.isFinite(value)) return fallback;
  const clamped = Math.min(range.max, Math.max(range.min, value));
  const snapped = range.min + Math.round((clamped - range.min) / range.step) * range.step;
  // Two decimals removes binary noise such as 0.15000000000000002.
  return Number(Math.min(range.max, snapped).toFixed(2));
}

/** True when `value` is one of the registered strategy names. */
export function isStrategyName(value: unknown): value is StrategyName {
  return STRATEGY_OPTIONS.some((option) => option.name === value);
}

/**
 * Apply `patch` to `current`, normalising every number. An unknown strategy
 * name is ignored so the panel can never request an unregistered strategy.
 */
export function applyRunSettings(current: RunSettings, patch: Partial<RunSettings>): RunSettings {
  const merged = { ...current, ...patch };
  return {
    strategy: isStrategyName(merged.strategy) ? merged.strategy : current.strategy,
    max_hold_time: snapToRange(merged.max_hold_time, MAX_HOLD_RANGE, current.max_hold_time),
    irregularity_threshold: snapToRange(
      merged.irregularity_threshold, THRESHOLD_RANGE, current.irregularity_threshold),
  };
}

/** Label of a strategy as shown on its card; the raw name if it is unknown. */
export function strategyLabel(name: string): string {
  return STRATEGY_OPTIONS.find((option) => option.name === name)?.label ?? name;
}

/** A duration in whole seconds with its unit, for example "45 s". */
export function formatSeconds(value: number): string {
  return `${value} s`;
}

/** The dimensionless threshold with two decimals, for example "0.25". */
export function formatThreshold(value: number): string {
  return value.toFixed(2);
}

/**
 * Build the exact JSON body for `POST /simulation/run`.
 *
 * `irregularity_threshold` is required for Adaptive and must be left out for
 * every other strategy: the API answers 422 if the key is present at all, even
 * as null, so it is added conditionally rather than set to undefined.
 */
export function buildRunRequest(connectionId: string, settings: RunSettings): RunRequestBody {
  const body: RunRequestBody = {
    connection_id: connectionId,
    strategy: settings.strategy,
    max_hold_time: settings.max_hold_time,
  };
  if (settings.strategy === "adaptive") {
    body.irregularity_threshold = settings.irregularity_threshold;
  }
  return body;
}
