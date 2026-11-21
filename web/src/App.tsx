// AI contribution: 50% or more AI-generated
/**
 * Station view shell: header with the connection selector, the Canvas map,
 * the clock, rules and decision panels, and the playback timeline.
 *
 * On start it registers the mock run catalog so the view works offline. When
 * an API URL is configured, every connection the user selects is then swapped
 * for that connection's simulator run output (#79); all panels read the run
 * and playback position from the shared Zustand store, so they switch together.
 * The run settings panel re-runs the selected connection with chosen settings.
 */

import { useEffect } from "react";
import { PlaybackTimeline } from "./components/PlaybackTimeline";
import { StationCanvas } from "./components/station-canvas";
import { ConnectionSelector } from "./components/connection-selector";
import { connectionRuns } from "./data/connection-runs";
import { stationViewData } from "./data/stationViewData";
import { SimulationClock } from "./components/simulation-clock";
import { OperatingRulesPanel } from "./components/operating-rules-panel";
import { DecisionView } from "./components/decision-view";
import { startPlaybackClock } from "./lib/playback-clock";
import {
  configuredApiUrl,
  createConnectionCatalogLoader,
  createConnectionRunLoader,
  runSimulation,
  type ConnectionCatalogLoader,
  type ConnectionRunLoader,
  type ScenarioRunner,
} from "./lib/simulation-api";
import { RunSettingsPanel } from "./components/run-settings-panel";
import { RunSummary } from "./components/run-summary";
import { PlaybackControls } from "./components/playback-controls";
import { SpeedSelector } from "./components/speed-selector";
import { DelayChart } from "./components/DelayChart";
import { usePlaybackStore, type RunStatus } from "./store/usePlaybackStore";

// Built once per page load. Without VITE_API_URL the app stays on its bundled
// mock runs, which is also what the component tests render.
const apiUrl = configuredApiUrl();
const defaultRunLoader = apiUrl === null ? null : createConnectionRunLoader(apiUrl);
// "Run scenario" sends the panel's settings to the same API.
const defaultScenarioRunner: ScenarioRunner | null = apiUrl === null
  ? null
  : (connectionId, settings, signal) =>
      runSimulation(connectionId, settings, { baseUrl: apiUrl, signal });
// Lists the backend's real connections for the selector (#76); null keeps
// the selector on the bundled fixture catalog, as before this endpoint.
const defaultConnectionCatalogLoader: ConnectionCatalogLoader | null = apiUrl === null
  ? null
  : createConnectionCatalogLoader(apiUrl);

// Subtitle under the heading, so viewers always know whether they are looking
// at simulator output or synthetic data.
const RUN_STATUS_TEXT: Record<RunStatus, string> = {
  mock: "Mock playback · synthetic passenger and train data",
  loading: "Loading simulation run…",
  simulated: "Simulation run · demo scenario output",
  error: "Showing mock playback · simulation run unavailable",
};
// A failed re-run leaves the earlier simulator output on screen, not a mock.
const RERUN_FAILED_TEXT = "Run failed · showing the previous simulation run";

interface AppProps {
  // Injectable for tests; null keeps the app on the mock catalog.
  runLoader?: ConnectionRunLoader | null;
  // Injectable for tests; null disables "Run scenario".
  scenarioRunner?: ScenarioRunner | null;
  // Injectable for tests; null keeps the selector on the bundled fixture catalog.
  connectionCatalogLoader?: ConnectionCatalogLoader | null;
}

export default function App({
  runLoader = defaultRunLoader,
  scenarioRunner = defaultScenarioRunner,
  connectionCatalogLoader = defaultConnectionCatalogLoader,
}: Readonly<AppProps>) {
  useEffect(startPlaybackClock, []);
  const runStatus = usePlaybackStore((state) => state.runStatus);
  const runError = usePlaybackStore((state) => state.runError);
  const data = usePlaybackStore(
    (state) => state.data
  );
  const selectedConnectionId = usePlaybackStore(
    (state) => state.selectedConnectionId
  );
  // The heading must persistently name the connection the user selected, even
  // when a run bundles more than one connection, not just data?.connections[0].
  const selectedConnection =
    data?.connections.find((connection) => connection.id === selectedConnectionId) ??
    data?.connections[0];
  const showsSimulatorOutput = usePlaybackStore((state) =>
    selectedConnectionId !== null && state.simulatedConnectionIds.includes(selectedConnectionId));
  const statusText = runStatus === "error" && showsSimulatorOutput
    ? RERUN_FAILED_TEXT
    : RUN_STATUS_TEXT[runStatus];

  useEffect(() => {
    const store = usePlaybackStore.getState();

    if (store.data === null) {
      store.setAvailableRuns(connectionRuns);
      store.loadData(stationViewData);
    }
  }, []);

  // Replace the bundled fixture catalog with the backend's real connection
  // list (#76) once it loads. A failed request leaves the fixture catalog
  // shown; per-connection run errors are reported separately via runStatus.
  useEffect(() => {
    if (connectionCatalogLoader === null) return;
    const controller = new AbortController();
    connectionCatalogLoader(controller.signal)
      .then((connections) => {
        if (!controller.signal.aborted) {
          usePlaybackStore.getState().setAvailableConnections(connections);
        }
      })
      .catch(() => {
        // Keep the bundled fixture catalog shown; nothing to report here.
      });
    return () => controller.abort();
  }, [connectionCatalogLoader]);

  // Each selection change requests that connection's run output. Leaving the
  // connection aborts the request so its late response cannot replace the
  // newer selection (the store also checks, for loaders that ignore aborts).
  useEffect(() => {
    if (runLoader === null || selectedConnectionId === null) return;
    const controller = new AbortController();
    void usePlaybackStore
      .getState()
      .loadConnectionRun(selectedConnectionId, runLoader, controller.signal);
    return () => controller.abort();
  }, [runLoader, selectedConnectionId]);

  return (
    <div className="app-shell">

      {/* APPLICATION HEADER */}
      <header className="topbar">

        <div className="brand">

          <div
            className="brand-mark"
            aria-hidden="true"
          >
            ↔
          </div>

          <div className="brand-text">

            <strong>
              TransitSync
            </strong>

            <small>
              Metro-REM transfer coordination
            </small>

          </div>

        </div>

        <ConnectionSelector />
      </header>

      {/* APPLICATION WORKSPACE */}
      <div className="workspace">

        {/* SIDEBAR */}
        <aside className="sidebar">

          <div className="section-label">
            Workspace
          </div>

          <div className="nav-current">
            Station view
          </div>

        </aside>

        {/* DASHBOARD */}
        <main className="content">

          {/* STATION VIEW */}
          <section
            className="panel station-region"
            aria-label="Station view"
          >
            <div className="station-heading">
              <span className="clock-heading">Selected connection</span>
              <h1>{selectedConnection?.label ?? "Choose a connection"}</h1>
              {/* <output> is natively a live status region, so no ARIA role is needed. */}
              <output className="station-status" title={runError ?? undefined}>
                {statusText}
              </output>
              <RunSummary />
            </div>
            <StationCanvas />
          </section>

          {/* RIGHT-HAND PANELS */}
          <aside className="inspector">

            {/* SIMULATION TIME */}
            <SimulationClock />

            {/* OPERATING RULES */}
            <OperatingRulesPanel />

            {/* DECISIONS */}
            <DecisionView />

          </aside>

          {/* PLAYBACK TIMELINE */}
          <section className="panel playback-region">
            <PlaybackControls />
            <PlaybackTimeline />
            <SpeedSelector />

          </section>

          {/* RESULTS */}
          <DelayChart />

          {/* RUN SETTINGS */}
          <RunSettingsPanel runner={scenarioRunner} />

        </main>

      </div>

    </div>
  );
}
