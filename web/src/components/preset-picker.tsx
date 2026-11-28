// AI contribution: 50% or more AI-generated
/**
 * Time-of-day preset picker of the Scenario setup view (#260 to #263).
 *
 * Lists the presets the API returned, marks the selected one, and shows the
 * five conditions it sets. Selecting a preset copies its values into the run
 * settings draft (`presetPatch`), so the parameter controls below move to
 * them and the next run sends them with the preset's name. "Custom" keeps the
 * current values and runs the default weekday-morning window.
 *
 * Only presets from the server are offered, so an unknown name can never be
 * selected. Changing a control after picking a preset keeps the preset's time
 * window and says that its values were changed.
 */
import { useId } from "react";
import { formatHeadway, formatPassengers, formatSeconds } from "../lib/run-settings";
import { presetPatch, presetDurationLabel, presetStartLabel } from "../lib/scenario-presets";
import { useRunSettingsStore } from "../store/useRunSettingsStore";
import type { RunSettings, ScenarioPreset } from "../types/runSettings";

interface PresetPickerProps {
  /** Presets from GET /scenario/presets; an empty list hides the picker. */
  presets: readonly ScenarioPreset[];
}

/** True when the draft still holds every value `preset` set. */
function matchesPreset(draft: RunSettings, preset: ScenarioPreset): boolean {
  const patch = presetPatch(preset);
  return (Object.keys(patch) as (keyof RunSettings)[])
    .every((key) => draft[key] === patch[key]);
}

/** The preset buttons, then the conditions of the selected preset. */
export function PresetPicker({ presets }: Readonly<PresetPickerProps>) {
  const groupName = useId();
  const draft = useRunSettingsStore((state) => state.draft);
  const update = useRunSettingsStore((state) => state.update);
  if (presets.length === 0) return null;
  const selected = presets.find((preset) => preset.name === draft.preset) ?? null;

  return (
    <fieldset className="preset-picker">
      <legend>Time of day</legend>
      <label className="strategy-option">
        <input type="radio" name={groupName} checked={selected === null}
          onChange={() => update({ preset: null })} />
        <span className="strategy-text">
          Custom
          <small>Weekday 07:00 with the values set below.</small>
        </span>
      </label>
      {presets.map((preset) => (
        <label key={preset.name} className="strategy-option">
          <input type="radio" name={groupName} checked={selected?.name === preset.name}
            onChange={() => update(presetPatch(preset))} />
          <span className="strategy-text">
            {preset.label}
            <small>Starts {presetStartLabel(preset)}, {presetDurationLabel(preset)}.</small>
          </span>
        </label>
      ))}
      {selected !== null && (
        <>
          <dl className="preset-conditions" aria-label={`${selected.label} conditions`}>
            <dt>Transfer volume</dt>
            <dd>{formatPassengers(selected.conditions.transfer_volume)}</dd>
            <dt>Train frequency</dt>
            <dd>{formatHeadway(selected.conditions.train_headway_s ?? null)}</dd>
            <dt>Onboard load</dt>
            <dd>{formatPassengers(selected.conditions.onboard_load)}</dd>
            <dt>Walking time</dt>
            <dd>{formatSeconds(selected.conditions.walking_mean_s)}</dd>
            <dt>Maximum hold</dt>
            <dd>{formatSeconds(selected.conditions.max_hold_time)}</dd>
          </dl>
          {!matchesPreset(draft, selected) && (
            <p className="setting-note">
              Some values were changed below; the run uses the changed values.
            </p>
          )}
        </>
      )}
    </fieldset>
  );
}
