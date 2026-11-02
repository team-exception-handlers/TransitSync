// AI contribution: 50% or more AI-generated

import { useEffect } from "react";

import { stationViewData } from "./data/stationViewData";
import { usePlaybackStore } from "./store/usePlaybackStore";


export default function App() {
  useEffect(() => {
    const store = usePlaybackStore.getState();

    if (store.data === null) {
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
              Metro–REM transfer coordination
            </small>

          </div>

        </div>

      </header>

      {/* APPLICATION WORKSPACE */}
      <div className="workspace">

        {/* SIDEBAR — APP SHELL ONLY */}
        <aside className="sidebar">

          <div className="section-label">
            Workspace
          </div>

          <div className="nav-current">
            Station view
          </div>

        </aside>

        {/* MAIN APPLICATION AREA */}
        <main className="content">

          {/* EMPTY STATION VIEW REGION */}
          <div className="panel station-region" />

          {/* EMPTY RIGHT-HAND REGIONS */}
          <div className="inspector">

            <div className="panel" />

            <div className="panel" />

            <div className="panel" />

          </div>

          {/* EMPTY BOTTOM REGION */}
          <div className="panel playback-region" />

        </main>

      </div>

    </div>
  );
}