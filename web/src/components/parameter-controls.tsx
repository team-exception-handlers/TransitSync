// AI contribution: 50% or more AI-generated
/**
 * Scenario parameter controls of the Scenario setup view (#251 to #255):
 * transfer volume, train frequency, onboard load, walking time and the
 * maximum hold from US-2.4, each showing its current value.
 *
 * Every control edits the run settings draft, which snaps values into the
 * ranges in lib/run-settings.ts (the backend's ranges), so what is shown is
 * what the next run sends (#257). Each slider also takes a typed value; a bad
 * one is reported through `onEntryError` so the panel can block the run (#256).
 */
import {
  DEFAULT_CUSTOM_HEADWAY_S,
  MAX_HOLD_RANGE,
  ONBOARD_LOAD_RANGE,
  TRAIN_HEADWAY_RANGE,
  TRANSFER_VOLUME_RANGE,
  WALKING_TIME_RANGE,
  formatPassengers,
  formatSeconds,
} from "../lib/run-settings";
import { useRunSettingsStore } from "../store/useRunSettingsStore";
import type { ParameterProvenanceMap } from "../types/provenance";
import { ProvenanceBadge } from "./provenance-badge";
import { SettingChoice } from "./setting-choice";
import { SettingSlider } from "./setting-slider";

// Help text in plain language; terms are defined for a first-time user.
const HELP = {
  transfer_volume: "How many passengers get off each REM train to transfer to the metro.",
  train_frequency: "How often a metro train leaves the connecting platform. Timetable uses "
    + "the real schedule; Custom runs a train every chosen number of seconds.",
  onboard_load: "Passengers already on each metro train. A hold delays every one of them.",
  walking_mean_s: "Average time a transferring passenger takes to walk between platforms.",
  max_hold_time: "The longest any train may wait for transfers, whatever the strategy asks for.",
};
const FREQUENCY_MODES = ["timetable", "custom"] as const;

interface ParameterControlsProps {
  /** Parameter sources from GET /parameters, shown as a badge under each control. */
  provenance?: ParameterProvenanceMap;
  /** Called with a control's key and its typed-entry error, or null when it is valid. */
  onEntryError: (key: string, error: string | null) => void;
}

/** The five parameter rows, in the order of the Scenario setup mockup. */
export function ParameterControls({ provenance, onEntryError }: Readonly<ParameterControlsProps>) {
  const draft = useRunSettingsStore((state) => state.draft);
  const update = useRunSettingsStore((state) => state.update);
  // null means "follow the timetable"; any number is a custom headway.
  const headway = draft.train_headway_s;

  return (
    <fieldset className="parameter-controls">
      <legend>Conditions</legend>
      {/* Each row reports its typed-entry error under its own key, so the
          panel can list them and clearing one never hides another. */}
      <SettingSlider label="Transfer volume" value={draft.transfer_volume}
        range={TRANSFER_VOLUME_RANGE} format={formatPassengers} help={HELP.transfer_volume}
        onValidity={(error) => onEntryError("transfer_volume", error)}
        onChange={(value) => update({ transfer_volume: value })} />
      <ProvenanceBadge parameterKey="transfer_volume" label="Transfer volume"
        provenance={provenance?.transfer_volume} />

      {/* Two modes rather than one slider: the timetable has no single
          headway value, so it cannot be a position on the slider. */}
      <SettingChoice label="Train frequency" options={FREQUENCY_MODES}
        value={headway === null ? "timetable" : "custom"}
        format={(mode) => (mode === "timetable" ? "Timetable" : "Custom")}
        note={HELP.train_frequency}
        onChange={(mode) => {
          // Back to Timetable removes the headway slider, so its typed-entry
          // error must go too, or it would keep "Run scenario" disabled.
          if (mode === "timetable") onEntryError("train_headway_s", null);
          update({ train_headway_s: mode === "timetable" ? null : DEFAULT_CUSTOM_HEADWAY_S });
        }} />
      {/* The slider only exists for a custom headway, so it can never send one by accident. */}
      {headway !== null && (
        <SettingSlider label="Time between trains" value={headway}
          range={TRAIN_HEADWAY_RANGE} format={formatSeconds}
          onValidity={(error) => onEntryError("train_headway_s", error)}
          onChange={(value) => update({ train_headway_s: value })} />
      )}
      <ProvenanceBadge parameterKey="train_headway_s" label="Train frequency"
        provenance={provenance?.train_headway_s} />

      <SettingSlider label="Onboard load" value={draft.onboard_load}
        range={ONBOARD_LOAD_RANGE} format={formatPassengers} help={HELP.onboard_load}
        onValidity={(error) => onEntryError("onboard_load", error)}
        onChange={(value) => update({ onboard_load: value })} />
      <ProvenanceBadge parameterKey="onboard_load" label="Onboard load"
        provenance={provenance?.onboard_load} />

      <SettingSlider label="Walking time" value={draft.walking_mean_s}
        range={WALKING_TIME_RANGE} format={formatSeconds} help={HELP.walking_mean_s}
        onValidity={(error) => onEntryError("walking_mean_s", error)}
        onChange={(value) => update({ walking_mean_s: value })} />
      <ProvenanceBadge parameterKey="walking_mean_s" label="Walking time"
        provenance={provenance?.walking_mean_s} />

      {/* Maximum hold from US-2.4 sits with the conditions, as #251 asks. */}
      <SettingSlider label="Maximum hold" value={draft.max_hold_time}
        range={MAX_HOLD_RANGE} format={formatSeconds} help={HELP.max_hold_time}
        onValidity={(error) => onEntryError("max_hold_time", error)}
        onChange={(value) => update({ max_hold_time: value })} />
      <ProvenanceBadge parameterKey="max_hold_time" label="Maximum hold"
        provenance={provenance?.max_hold_time} />
    </fieldset>
  );
}
