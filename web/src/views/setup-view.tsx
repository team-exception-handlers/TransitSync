// AI contribution: 50% or more AI-generated
/**
 * Scenario setup screen (#408): the run settings panel, moved here from the
 * bottom of the station view. A run started here replaces the run in
 * `usePlaybackStore`, so the station view and results show it straight away.
 */
import { RunSettingsPanel } from "../components/run-settings-panel";
import type { ScenarioRunner } from "../lib/simulation-api";

interface SetupViewProps {
  /** Sends one run to the API; null when no API is configured (mock runs only). */
  runner: ScenarioRunner | null;
}

/** Wrap the run settings panel with this screen's title. */
export function SetupView({ runner }: Readonly<SetupViewProps>) {
  return (
    <>
      <h1 className="view-title">Scenario setup</h1>
      <RunSettingsPanel runner={runner} />
    </>
  );
}
