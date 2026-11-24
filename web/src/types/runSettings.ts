// AI contribution: 50% or more AI-generated
/**
 * Run settings the Scenario setup view edits, sent to `POST /simulation/run`
 * (api/simulation_run.py, SimulationRunRequest). Field names are the backend's
 * snake_case names on purpose: the request model forbids unknown fields, so a
 * renamed key would be rejected with HTTP 422.
 *
 * The request body type is generated from the API's OpenAPI schema
 * (`npm run gen:api`, #267), so a backend field change breaks `tsc` here
 * instead of failing at run time.
 */
import type { components } from "./api.generated";

/** Strategy names registered in simulator/control/strategies/__init__.py. */
export type StrategyName =
  | "no_control"
  | "schedule_based"
  | "headway_regulation"
  | "connection_protection"
  | "rolling_horizon"
  | "adaptive";

/** Prepared disruption choices; none preserves the baseline run. */
export type DisruptionPreset =
  | "none"
  | "platform_delay"
  | "line_suspension"
  | "uneven_headways";

/** The values the run settings panel edits, in backend units. */
export interface RunSettings {
  strategy: StrategyName;
  /** Longest hold any train may get, in seconds (5 to 300, multiple of 5). */
  max_hold_time: number;
  /**
   * Mean headway deviation above which Adaptive switches mode. Dimensionless
   * (a fraction of the target gap between trains), not seconds. Kept in the
   * settings for every strategy, but only sent when the strategy is Adaptive.
   */
  irregularity_threshold: number;
  /**
   * Prediction-error size (kappa) applied to every estimate a strategy sees,
   * from 0 to 3. At 0 the strategy decides on the true values.
   */
  error_magnitude: number;
  /** Time-of-day preset whose window the run uses; null is the weekday-morning file. */
  preset: string | null;
  /** Transferring passengers per REM train arrival (M), 0 to 200. */
  transfer_volume: number;
  /**
   * Connecting metro headway in seconds (120 to 600, steps of 30), or null to
   * keep the GTFS timetable.
   */
  train_headway_s: number | null;
  /** Passengers already on each train (L), 0 to 800 in steps of 10. */
  onboard_load: number;
  /** Mean transfer walking time in seconds, 45 to 600 in steps of 5. */
  walking_mean_s: number;
  /** Legacy compatibility value; the preset picker is the user-facing control. */
  disruption_enabled: boolean;
  disruption_preset?: DisruptionPreset;
  /** Disruption start in relative simulation seconds. */
  disruption_time_s?: number;
  /** Seconds of delay or suspension duration (headway magnitude is seconds). */
  disruption_magnitude?: number;
}

/** JSON body of one run request, exactly as the API schema defines it. */
export type RunRequestBody = components["schemas"]["SimulationRunRequest"];

/** One time-of-day preset from `GET /scenario/presets` (#261). */
export type ScenarioPreset = components["schemas"]["ScenarioPreset"];

/** The five values a preset sets (#262). */
export type PresetConditions = components["schemas"]["PresetConditions"];
