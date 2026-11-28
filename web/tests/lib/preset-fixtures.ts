// AI contribution: 50% or more AI-generated
/** Presets shaped like `GET /scenario/presets`, shared by the preset tests. */
import type { ScenarioPreset } from "../../src/types/runSettings";

export const MORNING: ScenarioPreset = {
  name: "weekday_morning",
  label: "Weekday morning peak",
  start_time: "07:00:00",
  duration_s: 3600,
  conditions: {
    transfer_volume: 80, train_headway_s: null, onboard_load: 450,
    walking_mean_s: 130, max_hold_time: 60,
  },
};

export const SUNDAY: ScenarioPreset = {
  name: "sunday_morning",
  label: "Sunday morning",
  start_time: "10:00:00",
  duration_s: 3600,
  conditions: {
    transfer_volume: 30, train_headway_s: 480, onboard_load: 120,
    walking_mean_s: 110, max_hold_time: 120,
  },
};
