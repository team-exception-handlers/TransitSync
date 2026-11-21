// AI contribution: 50% or more AI-generated
/**
 * Compare screen (US-4.1, #230): the selected connection run with and without
 * holding, side by side, from the same starting conditions.
 *
 * Both runs come from one `/simulation/comparison` request, so they share the
 * scenario's service date and master seed (common random numbers). Both
 * canvases read the time from `usePlaybackStore`, so the one playback bar
 * below them plays, pauses, rewinds and seeks both panels together.
 */
import { useEffect } from "react";

import { ComparisonPanelStats } from "../components/comparison-panel-stats";
import { PlaybackControls } from "../components/playback-controls";
import { PlaybackTimeline } from "../components/PlaybackTimeline";
import { SpeedSelector } from "../components/speed-selector";
import { StationCanvas } from "../components/station-canvas";
import { strategyLabel } from "../lib/run-settings";
import type { ComparisonRunner } from "../lib/simulation-api";
import { useComparisonStore, type ComparisonStatus } from "../store/useComparisonStore";
import { usePlaybackStore } from "../store/usePlaybackStore";
import { useRunSettingsStore } from "../store/useRunSettingsStore";
import type { StationViewData } from "../types/stationView";
import "./compare-view.css";

interface CompareViewProps {
  /** Runs both sides; null when no API is configured. */
  runner: ComparisonRunner | null;
}

// Status line under the heading for each loading state.
const STATUS_TEXT: Record<ComparisonStatus, string> = {
  idle: "Choose a connection to compare",
  loading: "Running both simulations…",
  ready: "Both runs loaded · one shared playback clock",
  error: "Comparison failed",
};

/**
 * Load the pair for the selected connection and its settings, and restart
 * playback at 0 when a new pair arrives so both sides begin together.
 * Settings are the ones last run for this connection, else the panel draft.
 */
function useComparisonLoader(runner: ComparisonRunner | null) {
  const connectionId = usePlaybackStore((state) => state.selectedConnectionId);
  const settings = useRunSettingsStore((state) =>
    (connectionId === null ? undefined : state.applied[connectionId]) ?? state.draft);

  useEffect(() => {
    if (runner === null || connectionId === null) return;
    const controller = new AbortController();
    void useComparisonStore.getState()
      .loadComparison(connectionId, settings, runner, controller.signal)
      .then((loaded) => {
        if (loaded) usePlaybackStore.getState().seek(0);
      });
    return () => controller.abort();
  }, [runner, connectionId, settings]);
}

interface ComparisonPanelProps {
  title: string;
  run: StationViewData;
}

/** One labelled side: its view-only canvas and its holding stats. */
function ComparisonPanel({ title, run }: Readonly<ComparisonPanelProps>) {
  return (
    <section className="panel comparison-panel" aria-label={title}>
      <h2 className="comparison-panel-title">{title}</h2>
      <StationCanvas data={run} interactive={false} label={title} />
      <ComparisonPanelStats run={run} />
    </section>
  );
}

/** The heading, both panels and the shared playback bar. */
export function CompareView({ runner }: Readonly<CompareViewProps>) {
  useComparisonLoader(runner);
  // Whole-store subscription: every field here is shown, and it only changes
  // on a load, not on each clock tick.
  const comparison = useComparisonStore();
  // Heading names the connection the shared selector picked.
  const connectionLabel = usePlaybackStore((state) =>
    state.data?.connections.find((item) => item.id === state.selectedConnectionId)?.label);

  if (runner === null) {
    return (
      <>
        <h1 className="view-title">Compare</h1>
        <p className="panel view-message">
          Comparing runs needs the simulation API. Set VITE_API_URL and restart
          the app to run holding and no-holding side by side.
        </p>
      </>
    );
  }

  const { holding, noHolding, startingConditions, holdingStrategy } = comparison;
  // Panels appear only once a full pair exists; a failed reload keeps the old
  // pair, so the alert shows above runs that are still valid to compare.
  // No holding comes first, matching the reading order "before → after".
  return (
    <>
      <div className="comparison-heading">
        <h1 className="view-title">Compare · {connectionLabel ?? "No connection"}</h1>
        {startingConditions && (
          <p className="comparison-conditions">
            Same starting conditions: {startingConditions.serviceDate} · seed{" "}
            {startingConditions.masterSeed}
          </p>
        )}
        {/* <output> is natively a live status region, so no ARIA role is needed. */}
        <output className="station-status">{STATUS_TEXT[comparison.status]}</output>
        {comparison.error && (
          <p className="comparison-error" role="alert">{comparison.error}</p>
        )}
      </div>

      {holding && noHolding && holdingStrategy && (
        <div className="comparison-panels">
          <ComparisonPanel title="No holding" run={noHolding} />
          <ComparisonPanel
            title={`With holding · ${strategyLabel(holdingStrategy)}`} run={holding} />
        </div>
      )}

      {/* The same controls as the station view: they drive the one shared
          clock, so a single bar moves both panels. */}
      <section className="panel playback-region" aria-label="Shared playback">
        <PlaybackControls />
        <PlaybackTimeline />
        <SpeedSelector />
      </section>
    </>
  );
}
