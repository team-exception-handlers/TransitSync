// AI contribution: 50% or more AI-generated

import { useEffect } from "react";
import { PlaybackTimeline } from "./components/PlaybackTimeline";
import { StationCanvas } from "./components/station-canvas";
import { ConnectionSelector } from "./components/connection-selector";
import { connectionRuns } from "./data/connection-runs";
import { stationViewData } from "./data/stationViewData";
import { formatTime } from "./lib/time";
import { startPlaybackClock } from "./lib/playback-clock";
import { PlaybackControls } from "./components/playback-controls";
import { usePlaybackStore } from "./store/usePlaybackStore";


export default function App() {
  useEffect(startPlaybackClock, []);
  const data = usePlaybackStore(
    (state) => state.data
  );

  const currentTime = usePlaybackStore(
    (state) => state.currentTime_s
  );

  useEffect(() => {
    const store = usePlaybackStore.getState();

    if (store.data === null) {
      store.setAvailableRuns(connectionRuns);
      store.loadData(stationViewData);
    }
  }, []);

  const displayedTime = formatTime(
    currentTime,
    data?.start_clock_s ?? 0
  );

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
              <h1>{data?.connections[0]?.label ?? "Choose a connection"}</h1>
              <small>Mock playback · synthetic passenger and train data</small>
            </div>
            <StationCanvas />
          </section>

          {/* RIGHT-HAND PANELS */}
          <aside className="inspector">

            {/* SIMULATION TIME */}
            <section className="panel clock-panel">

              <div className="clock-heading">
                Simulation clock
              </div>

              <div className="clock-digits">
                {displayedTime}
              </div>

            </section>

            {/* EMPTY SECTION */}
            <div className="panel" />

            {/* EMPTY SECTION */}
            <div className="panel" />

          </aside>

          {/* PLAYBACK TIMELINE */}
          <section className="panel playback-region">
            <PlaybackControls />
            <PlaybackTimeline />

          </section>

        </main>

      </div>

    </div>
  );
}
