// AI contribution: 50% or more AI-generated
/**
 * Time-of-day presets for the Scenario setup view (#260 to #263).
 *
 * The presets and their values live on the server (`PRESET_SETTINGS` in
 * simulator/scenario.py) and come from `GET /scenario/presets`, so the page
 * can only offer presets the run endpoint accepts. Picking one copies its
 * values into the run settings draft (`presetPatch`), where the controls show
 * them and the next run sends them along with the preset's name.
 */
import type { PresetConditions, RunSettings, ScenarioPreset } from "../types/runSettings";

/** Loads the preset list; the setup view accepts any function of this shape. */
export type PresetLoader = (signal?: AbortSignal) => Promise<ScenarioPreset[]>;

const CONDITION_KEYS = [
  "transfer_volume", "onboard_load", "walking_mean_s", "max_hold_time",
] as const;

/** True when every condition is a finite number; the headway may also be null. */
function isConditions(value: unknown): value is PresetConditions {
  if (typeof value !== "object" || value === null) return false;
  const item = value as Record<string, unknown>;
  const headway = item.train_headway_s;
  return CONDITION_KEYS.every((key) => Number.isFinite(item[key]))
    && (headway === null || headway === undefined || Number.isFinite(headway));
}

/** True when one entry has a name, a label, a start time and valid conditions. */
function isPreset(value: unknown): value is ScenarioPreset {
  if (typeof value !== "object" || value === null) return false;
  const item = value as Record<string, unknown>;
  return typeof item.name === "string" && item.name.length > 0
    && typeof item.label === "string" && item.label.length > 0
    && typeof item.start_time === "string"
    && Number.isFinite(item.duration_s) && (item.duration_s as number) > 0
    && isConditions(item.conditions);
}

/**
 * Validate the `/scenario/presets` body. Throws when it is not a list or an
 * entry is malformed, so the picker never offers a preset it cannot apply.
 */
export function parseScenarioPresets(payload: unknown): ScenarioPreset[] {
  if (!Array.isArray(payload) || !payload.every(isPreset)) {
    throw new Error("Invalid scenario preset list");
  }
  return payload;
}

/** GET `${baseUrl}/scenario/presets`; an HTTP failure throws a message safe to show. */
export function createPresetLoader(baseUrl: string, fetchImpl: typeof fetch = fetch): PresetLoader {
  return async (signal) => {
    const response = await fetchImpl(`${baseUrl}/scenario/presets`, { signal });
    if (!response.ok) {
      throw new Error(`Could not load the time-of-day presets (HTTP ${response.status}).`);
    }
    return parseScenarioPresets(await response.json());
  };
}

/**
 * The draft change that applies `preset` (#263): its name, so the run uses
 * its time window, and each of its five values, so the controls show them.
 * A missing headway means the preset follows the timetable.
 */
export function presetPatch(preset: ScenarioPreset): Partial<RunSettings> {
  const { conditions } = preset;
  return {
    preset: preset.name,
    transfer_volume: conditions.transfer_volume,
    train_headway_s: conditions.train_headway_s ?? null,
    onboard_load: conditions.onboard_load,
    walking_mean_s: conditions.walking_mean_s,
    max_hold_time: conditions.max_hold_time,
  };
}

/** "07:00" from "07:00:00". */
export function presetStartLabel(preset: ScenarioPreset): string {
  return preset.start_time.slice(0, 5);
}

/**
 * The preset's window length in words, from the API's `duration_s`, so a
 * longer preset is never described as "one hour": "one hour", "2 hours",
 * "90 min" (rounded to the minute when it is not a whole number of hours).
 */
export function presetDurationLabel(preset: ScenarioPreset): string {
  const hours = preset.duration_s / 3600;
  if (hours === 1) return "one hour";
  if (Number.isInteger(hours)) return `${hours} hours`;
  return `${Math.round(preset.duration_s / 60)} min`;
}
