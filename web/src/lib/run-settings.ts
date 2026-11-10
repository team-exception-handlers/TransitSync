// AI contribution: 50% or more AI-generated
/**
 * Single source of truth for run settings: the strategy list, the backend
 * defaults and the request body builder.
 *
 * The values copy api/simulation_run.py (SimulationRunRequest). Keeping them
 * next to the builder means the controls and the request can never disagree
 * about what the API accepts.
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

/** Backend defaults, plus the panel's starting threshold for Adaptive. */
export const DEFAULT_RUN_SETTINGS: RunSettings = {
  strategy: "no_control",
  max_hold_time: 300,
  irregularity_threshold: 0.25,
};

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
