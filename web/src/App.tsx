// AI contribution: 50% or more AI-generated

import { useEffect } from "react";
import { PlaybackTimeline } from "./components/PlaybackTimeline";
import { StationCanvas } from "./components/station-canvas";
import { ConnectionSelector } from "./components/connection-selector";
import { connectionRuns } from "./data/connection-runs";
import { stationViewData } from "./data/stationViewData";
import { SimulationClock } from "./components/simulation-clock";
import { startPlaybackClock } from "./lib/playback-clock";
import { PlaybackControls } from "./components/playback-controls";
import { SpeedSelector } from "./components/speed-selector";
import { usePlaybackStore } from "./store/usePlaybackStore";


export default function App() {
  useEffect(startPlaybackClock, []);
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
              <small>Mock playback · synthetic passenger and train data</small>
            </div>
            <StationCanvas />
          </section>

          {/* RIGHT-HAND PANELS */}
          <aside className="inspector">

            {/* SIMULATION TIME */}
            <SimulationClock />

            {/* EMPTY SECTION */}
            <div className="panel" />

            {/* EMPTY SECTION */}
            <div className="panel" />

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
