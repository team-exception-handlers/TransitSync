// AI contribution: 50% or more AI-generated
/**
 * Run settings panel of the Scenario setup view (#45, #50, #60, #183, #182,
 * #25): choose a strategy, the adaptive irregularity threshold, the
 * prediction-error magnitude and the demo disruption, plus the scenario
 * conditions (#251 to #257), then run the selected connection with those
 * values.
 *
 * Typed values are checked before a run (#256): while any entry is invalid,
 * "Run scenario" is disabled and the list above it names each bad setting.
 *
 * Controls only edit the draft in the run settings store. The simulator is
 * called when "Run scenario" is clicked, never on a change, because a run is
 * a full simulation and dragging a slider would queue dozens of them.
 */
import { useCallback, useEffect, useId, useRef, useState } from "react";
import {
  ERROR_MAGNITUDE_RANGE,
  DISRUPTION_MAGNITUDE_RANGE,
  DISRUPTION_PRESETS,
  DISRUPTION_TIME_RANGE,
  STRATEGY_OPTIONS,
  THRESHOLD_RANGE,
  formatErrorMagnitude,
  formatSeconds,
  formatThreshold,
} from "../lib/run-settings";
import type { DisruptionPreset } from "../types/runSettings";
import type { ScenarioRunner } from "../lib/simulation-api";
import type { ParameterProvenanceMap } from "../types/provenance";
import { usePlaybackStore } from "../store/usePlaybackStore";
import { useRunSettingsStore } from "../store/useRunSettingsStore";
import { SettingChoice } from "./setting-choice";
import { SettingSlider } from "./setting-slider";
import { ParameterControls } from "./parameter-controls";
import { ProvenanceBadge } from "./provenance-badge";
import "./run-settings.css";

const ERROR_MAGNITUDE_HELP =
  "How wrong the strategy's predictions are. At 0 it decides on the true values, "
  + "which gives the best result that strategy can reach.";
const DISRUPTION_HELP =
  "None leaves a baseline run. Platform delay delays the feeder train; line suspension "
  + "halts Green line dispatch; uneven headways vary dispatch gaps.";
const DISRUPTION_LABELS: Record<DisruptionPreset, string> = {
  none: "None",
  platform_delay: "Platform delay",
  line_suspension: "Line suspension",
  uneven_headways: "Uneven headways",
};

interface RunSettingsPanelProps {
  /** Sends one run to the API; null when no API is configured (mock runs only). */
  runner: ScenarioRunner | null;
  /** Parameter sources from GET /parameters, shown as a badge under each setting. */
  provenance?: ParameterProvenanceMap;
  /** Opens the Sources screen (#320); the link is hidden when not given. */
  onShowSources?: () => void;
}

/**
 * The panel reads the selected connection and run status from the playback
 * store, so it needs no props beyond the function that performs a run.
 */
export function RunSettingsPanel({ runner, provenance, onShowSources }: Readonly<RunSettingsPanelProps>) {
  const titleId = useId();
  const strategyGroup = useId();
  const draft = useRunSettingsStore((state) => state.draft);
  const update = useRunSettingsStore((state) => state.update);
  const reset = useRunSettingsStore((state) => state.reset);
  const connectionId = usePlaybackStore((state) => state.selectedConnectionId);
  const runStatus = usePlaybackStore((state) => state.runStatus);
  const runError = usePlaybackStore((state) => state.runError);
  const request = useRef<AbortController | null>(null);
  // Typed-entry errors by control key; empty when every entry is valid.
  const [entryErrors, setEntryErrors] = useState<Readonly<Record<string, string>>>({});
  // Stable, and returns the same object when nothing changed, so a row
  // reporting "still valid" on every render never re-renders the panel.
  const reportEntryError = useCallback((key: string, error: string | null) => {
    setEntryErrors((current) => {
      if ((current[key] ?? null) === error) return current;
      const next = { ...current };
      if (error === null) delete next[key];
      else next[key] = error;
      return next;
    });
  }, []);
  const errorList = Object.values(entryErrors);

  // A run belongs to the connection it was started for: leaving that
  // connection (or the page) cancels it so it cannot replace a newer view.
  useEffect(() => () => request.current?.abort(), [connectionId]);

  // "loading" also covers the automatic load after a connection change, so
  // a scenario cannot start while another response is still on its way.
  const isRunning = runStatus === "loading";
  const canRun = runner !== null && connectionId !== null && !isRunning
    && errorList.length === 0;

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
          {onShowSources && (
            <button type="button" className="playback-button" onClick={onShowSources}>
              Where these values come from
            </button>
          )}
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
      {/* Names every bad entry in one place, next to the disabled button. */}
      {errorList.length > 0 && (
        <div className="run-settings-error" role="alert">
          Fix these values before running:
          <ul>{errorList.map((error) => <li key={error}>{error}</li>)}</ul>
        </div>
      )}
      {/* The previous run stays on screen; this only explains why it did not change. */}
      {runStatus === "error" && runError !== null && (
        <p className="run-settings-error" role="alert">{runError}</p>
      )}

      <div className="run-settings-body">
        <fieldset className="strategy-list">
          {/* The badge sits after the legend, not inside it: the legend is the
              group's accessible name and should read just "Strategy". */}
          <legend>Strategy</legend>
          <ProvenanceBadge parameterKey="strategy" label="Strategy"
            provenance={provenance?.strategy} />
          {STRATEGY_OPTIONS.map((option) => (
            <label key={option.name} className="strategy-option">
              <input type="radio" name={strategyGroup} value={option.name}
                checked={draft.strategy === option.name}
                onChange={() => update({ strategy: option.name })} />
              {/* Name text sits directly in the span (no <b>) so the label's
                  text stays within the depth accessibility checkers read. */}
              <span className="strategy-text">
                {option.label}
                <small>{option.description}</small>
              </span>
            </label>
          ))}
          {/* Directly under the list, as in the mockup; only Adaptive reads it. */}
          <SettingSlider label="Irregularity threshold (adaptive only)"
            value={draft.irregularity_threshold} range={THRESHOLD_RANGE}
            format={formatThreshold} disabled={draft.strategy !== "adaptive"}
            onChange={(value) => update({ irregularity_threshold: value })} />
          <ProvenanceBadge parameterKey="irregularity_threshold" label="Irregularity threshold"
            provenance={provenance?.irregularity_threshold} />
        </fieldset>

        <div className="run-settings-values">
          <ParameterControls provenance={provenance} onEntryError={reportEntryError} />
          <SettingSlider label="Error magnitude" value={draft.error_magnitude}
            range={ERROR_MAGNITUDE_RANGE} format={formatErrorMagnitude}
            help={ERROR_MAGNITUDE_HELP}
            onChange={(value) => update({ error_magnitude: value })} />
          <ProvenanceBadge parameterKey="error_magnitude" label="Error magnitude"
            provenance={provenance?.error_magnitude} />
          <SettingChoice label="Disruption" options={DISRUPTION_PRESETS}
            value={draft.disruption_preset ?? "none"} format={(preset) => DISRUPTION_LABELS[preset]}
            note={DISRUPTION_HELP}
            onChange={(preset) => update({
              disruption_preset: preset,
              disruption_enabled: preset === "platform_delay",
            })} />
          <ProvenanceBadge parameterKey="disruption_enabled" label="Disruption"
            provenance={provenance?.disruption_enabled} />
          {(draft.disruption_preset ?? "none") !== "none" && (
            <>
              <SettingSlider label="Disruption start"
                value={draft.disruption_time_s ?? 120} range={DISRUPTION_TIME_RANGE}
                format={formatSeconds}
                onChange={(value) => update({ disruption_time_s: value })} />
              <SettingSlider
                label={(draft.disruption_preset ?? "none") === "line_suspension"
                  ? "Suspension duration"
                  : "Disruption magnitude"}
                value={draft.disruption_magnitude ?? 60}
                range={DISRUPTION_MAGNITUDE_RANGE}
                format={formatSeconds}
                onChange={(value) => update({ disruption_magnitude: value })} />
            </>
          )}
        </div>
      </div>
    </section>
  );
}
