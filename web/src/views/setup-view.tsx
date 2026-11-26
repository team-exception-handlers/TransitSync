// AI contribution: 50% or more AI-generated
/**
 * Scenario setup screen (#408): the run settings panel, moved here from the
 * bottom of the station view. A run started here replaces the run in
 * `usePlaybackStore`, so the station view and results show it straight away.
 *
 * The screen also shows the time-of-day presets' picker (#261) above the
 * panel, since picking one fills the panel's conditions. The presets are
 * loaded once by the app shell, like provenance, so leaving and reopening
 * this screen neither refetches them nor hides the picker meanwhile. If they
 * could not be loaded the picker stays hidden and a note says why; every
 * other setting still works.
 */
import { PresetPicker } from "../components/preset-picker";
import { RunSettingsPanel } from "../components/run-settings-panel";
import type { ScenarioRunner } from "../lib/simulation-api";
import type { ParameterProvenanceMap } from "../types/provenance";
import type { ScenarioPreset } from "../types/runSettings";

interface SetupViewProps {
  /** Sends one run to the API; null when no API is configured (mock runs only). */
  runner: ScenarioRunner | null;
  /** Where each setting came from (US-7.1), shown beside each run setting. */
  provenance?: ParameterProvenanceMap;
  /** Opens the Sources screen from "Where these values come from" (#320). */
  onShowSources?: () => void;
  /** Time-of-day presets loaded by the app shell; empty hides the picker. */
  presets?: readonly ScenarioPreset[];
  /** Why the presets could not be loaded, shown in place of the picker. */
  presetError?: string | null;
}

/** Wrap the run settings panel with this screen's title and its presets. */
export function SetupView({
  runner, provenance, onShowSources, presets = [], presetError = null,
}: Readonly<SetupViewProps>) {
  return (
    <>
      <h1 className="view-title">Scenario setup</h1>
      {presetError !== null && <p className="run-settings-note">{presetError}</p>}
      {presets.length > 0 && (
        <section className="panel run-settings" aria-label="Time-of-day presets">
          <PresetPicker presets={presets} />
        </section>
      )}
      <RunSettingsPanel runner={runner} provenance={provenance}
        onShowSources={onShowSources} />
    </>
  );
}
