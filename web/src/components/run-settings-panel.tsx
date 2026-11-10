// AI contribution: 50% or more AI-generated
/**
 * Run settings panel of the station view (#45, #50, #60): choose a strategy,
 * the maximum hold and the adaptive irregularity threshold, then run the
 * selected connection with those values.
 *
 * Controls only edit the draft in the run settings store. The simulator is
 * called when "Run scenario" is clicked, never on a change, because a run is
 * a full simulation and dragging a slider would queue dozens of them.
 */
import { useEffect, useId, useRef } from "react";
import {
  MAX_HOLD_RANGE,
  STRATEGY_OPTIONS,
  THRESHOLD_RANGE,
  formatSeconds,
  formatThreshold,
} from "../lib/run-settings";
import type { ScenarioRunner } from "../lib/simulation-api";
import { usePlaybackStore } from "../store/usePlaybackStore";
import { useRunSettingsStore } from "../store/useRunSettingsStore";
import { SettingSlider } from "./setting-slider";
import "./run-settings.css";

// Wording from the Scenario setup mockup's help popover.
const MAX_HOLD_HELP =
  "The longest any train may wait for transfers, whatever the strategy asks for.";

interface RunSettingsPanelProps {
  /** Sends one run to the API; null when no API is configured (mock runs only). */
  runner: ScenarioRunner | null;
}

/**
 * The panel reads the selected connection and run status from the playback
 * store, so it needs no props beyond the function that performs a run.
 */
export function RunSettingsPanel({ runner }: Readonly<RunSettingsPanelProps>) {
  const titleId = useId();
  const strategyGroup = useId();
  const draft = useRunSettingsStore((state) => state.draft);
  const update = useRunSettingsStore((state) => state.update);
  const reset = useRunSettingsStore((state) => state.reset);
  const connectionId = usePlaybackStore((state) => state.selectedConnectionId);
  const runStatus = usePlaybackStore((state) => state.runStatus);
  const runError = usePlaybackStore((state) => state.runError);
  const request = useRef<AbortController | null>(null);

  // A run belongs to the connection it was started for: leaving that
  // connection (or the page) cancels it so it cannot replace a newer view.
  useEffect(() => () => request.current?.abort(), [connectionId]);

  // "loading" also covers the automatic load after a connection change, so
  // a scenario cannot start while another response is still on its way.
  const isRunning = runStatus === "loading";
  const canRun = runner !== null && connectionId !== null && !isRunning;

  /** Send the current draft for the selected connection and label the result. */
  async function runScenario() {
    if (runner === null || connectionId === null) return;
    request.current?.abort();
    const controller = new AbortController();
    request.current = controller;
    // Read the draft once so the run and its label use the same values even
    // if a control changes while the request is in flight.
    const settings = useRunSettingsStore.getState().draft;
    const shown = await usePlaybackStore.getState().loadConnectionRun(
      connectionId,
      (id, signal) => runner(id, settings, signal),
      controller.signal,
      { rerun: true },
    );
    // Only a run that is now on screen may change the "settings used" label.
    if (shown) useRunSettingsStore.getState().markApplied(connectionId, settings);
  }

  return (
    <section className="panel run-settings" aria-labelledby={titleId}>
      <div className="run-settings-header">
        <h2 id={titleId} className="clock-heading">Run settings</h2>
        <div className="run-settings-actions">
          <button type="button" className="playback-button" onClick={reset}>
            Reset to defaults
          </button>
          <button type="button" className="playback-button primary" disabled={!canRun}
            onClick={() => void runScenario()}>
            {isRunning ? "Running…" : "Run scenario"}
          </button>
        </div>
      </div>

      {runner === null && (
        <p className="run-settings-note">
          No simulation API is configured, so only mock playback is available.
          Set VITE_API_URL to run scenarios.
        </p>
      )}
      {/* The previous run stays on screen; this only explains why it did not change. */}
      {runStatus === "error" && runError !== null && (
        <p className="run-settings-error" role="alert">{runError}</p>
      )}

      <div className="run-settings-body">
        <fieldset className="strategy-list">
          <legend>Strategy</legend>
          {STRATEGY_OPTIONS.map((option) => (
            <label key={option.name} className="strategy-option">
              <input type="radio" name={strategyGroup} value={option.name}
                checked={draft.strategy === option.name}
                onChange={() => update({ strategy: option.name })} />
              <span>
                <b>{option.label}</b>
                <small>{option.description}</small>
              </span>
            </label>
          ))}
          {/* Directly under the list, as in the mockup; only Adaptive reads it. */}
          <SettingSlider label="Irregularity threshold (adaptive only)"
            value={draft.irregularity_threshold} range={THRESHOLD_RANGE}
            format={formatThreshold} disabled={draft.strategy !== "adaptive"}
            onChange={(value) => update({ irregularity_threshold: value })} />
        </fieldset>

        <div className="run-settings-values">
          <SettingSlider label="Maximum hold" value={draft.max_hold_time}
            range={MAX_HOLD_RANGE} format={formatSeconds} help={MAX_HOLD_HELP}
            onChange={(value) => update({ max_hold_time: value })} />
        </div>
      </div>
    </section>
  );
}
