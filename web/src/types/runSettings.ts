// AI contribution: 50% or more AI-generated
/**
 * Front-end mirror of the run settings accepted by `POST /simulation/run`
 * (api/simulation_run.py, SimulationRunRequest). Field names are the backend's
 * snake_case names on purpose: the request model forbids unknown fields, so a
 * renamed key would be rejected with HTTP 422.
 */

/** Strategy names registered in simulator/control/strategies/__init__.py. */
export type StrategyName =
  | "no_control"
  | "schedule_based"
  | "headway_regulation"
  | "connection_protection"
  | "rolling_horizon"
  | "adaptive";

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
}

/** JSON body of one run request; the threshold key is absent unless Adaptive. */
export interface RunRequestBody {
  connection_id: string;
  strategy: StrategyName;
  max_hold_time: number;
  irregularity_threshold?: number;
}
