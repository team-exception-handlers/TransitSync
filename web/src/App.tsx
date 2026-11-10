// AI contribution: 50% or more AI-generated
/**
 * Station view shell: header with the connection selector, the Canvas map,
 * the clock, rules and decision panels, and the playback timeline.
 *
 * On start it registers the mock run catalog so the view works offline. When
 * an API URL is configured, every connection the user selects is then swapped
 * for that connection's simulator run output (#79); all panels read the run
 * and playback position from the shared Zustand store, so they switch together.
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
  createConnectionRunLoader,
  type ConnectionRunLoader,
} from "./lib/simulation-api";
import { PlaybackControls } from "./components/playback-controls";
import { SpeedSelector } from "./components/speed-selector";
import { usePlaybackStore, type RunStatus } from "./store/usePlaybackStore";

// Built once per page load. Without VITE_API_URL the app stays on its bundled
// mock runs, which is also what the component tests render.
const apiUrl = configuredApiUrl();
const defaultRunLoader = apiUrl === null ? null : createConnectionRunLoader(apiUrl);

// Subtitle under the heading, so viewers always know whether they are looking
// at simulator output or synthetic data.
const RUN_STATUS_TEXT: Record<RunStatus, string> = {
  mock: "Mock playback · synthetic passenger and train data",
  loading: "Loading simulation run…",
  simulated: "Simulation run · demo scenario output",
  error: "Showing mock playback · simulation run unavailable",
};

interface AppProps {
  // Injectable for tests; null keeps the app on the mock catalog.
  runLoader?: ConnectionRunLoader | null;
}

export default function App({ runLoader = defaultRunLoader }: Readonly<AppProps>) {
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

  useEffect(() => {
    const store = usePlaybackStore.getState();

    if (store.data === null) {
      store.setAvailableRuns(connectionRuns);
      store.loadData(stationViewData);
    }
  }, []);

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
              <small role="status" title={runError ?? undefined}>
                {RUN_STATUS_TEXT[runStatus]}
              </small>
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

        </main>

      </div>

    </div>
  );
}
