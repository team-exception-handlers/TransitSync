// AI contribution: 50% or more AI-generated
/**
 * Scenario setup screen (#408): the run settings panel, moved here from the
 * bottom of the station view. A run started here replaces the run in
 * `usePlaybackStore`, so the station view and results show it straight away.
 *
 * The screen also loads the time-of-day presets (#261) when it opens and shows
 * their picker above the panel, since picking one fills the panel's
 * conditions. If they cannot be loaded the picker stays hidden and a note
 * says why; every other setting still works.
 */
import { useEffect, useState } from "react";
import { PresetPicker } from "../components/preset-picker";
import { RunSettingsPanel } from "../components/run-settings-panel";
import type { PresetLoader } from "../lib/scenario-presets";
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
  /** Reads the time-of-day presets; null (no API) hides the preset picker. */
  presetLoader?: PresetLoader | null;
}

/** Wrap the run settings panel with this screen's title and its presets. */
export function SetupView({
  runner, provenance, onShowSources, presetLoader = null,
}: Readonly<SetupViewProps>) {
  const [presets, setPresets] = useState<ScenarioPreset[]>([]);
  const [presetError, setPresetError] = useState<string | null>(null);

  useEffect(() => {
    if (presetLoader === null) return;
    const controller = new AbortController();
    presetLoader(controller.signal)
      .then(setPresets)
      .catch((error: unknown) => {
        // Leaving the screen aborts the request; that is not a failure.
        if (controller.signal.aborted) return;
        setPresetError(error instanceof Error ? error.message : "Could not load presets.");
      });
    return () => controller.abort();
  }, [presetLoader]);

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
