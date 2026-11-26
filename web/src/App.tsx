// AI contribution: 50% or more AI-generated
/**
 * Application shell: header with the connection selector, the sidebar that
 * switches between the five workspace screens (#408), and the active screen.
 *
 * On start it registers the mock run catalog so the app works offline. When
 * an API URL is configured, every connection the user selects is then swapped
 * for that connection's simulator run output (#79). The loading effects and
 * the playback clock live here, not in a screen, so they keep running while
 * the user moves between screens and every screen shows the same run.
 */

import { useEffect, useState, type ReactNode } from "react";
import { ConnectionSelector } from "./components/connection-selector";
import { ProvenanceBadge } from "./components/provenance-badge";
import { SourcesView } from "./components/sources-view";
import { connectionRuns } from "./data/connection-runs";
import { stationViewData } from "./data/stationViewData";
import { startPlaybackClock } from "./lib/playback-clock";
import {
  configuredApiUrl,
  createConnectionCatalogLoader,
  createConnectionRunLoader,
  createParameterProvenanceLoader,
  runComparison,
  runSimulation,
  type ComparisonRunner,
  type ConnectionCatalogLoader,
  type ConnectionRunLoader,
  type ParameterProvenanceLoader,
  type ScenarioRunner,
} from "./lib/simulation-api";
import { usePlaybackStore } from "./store/usePlaybackStore";
import { VIEWS, useViewStore, type AppView } from "./store/useViewStore";
import { CompareView } from "./views/compare-view";
import { ResultsView } from "./views/results-view";
import { SetupView } from "./views/setup-view";
import { createPresetLoader, type PresetLoader } from "./lib/scenario-presets";
import { StationView } from "./views/station-view";
import type { ParameterProvenanceMap } from "./types/provenance";
import type { ScenarioPreset } from "./types/runSettings";

// Built once per page load. Without VITE_API_URL the app stays on its bundled
// mock runs, which is also what the component tests render.
const apiUrl = configuredApiUrl();
const defaultRunLoader = apiUrl === null ? null : createConnectionRunLoader(apiUrl);
// "Run scenario" sends the panel's settings to the same API.
const defaultScenarioRunner: ScenarioRunner | null = apiUrl === null
  ? null
  : (connectionId, settings, signal) =>
      runSimulation(connectionId, settings, { baseUrl: apiUrl, signal });
// The Compare screen runs holding and no holding through the same API (US-4.1).
const defaultComparisonRunner: ComparisonRunner | null = apiUrl === null
  ? null
  : (connectionId, settings, signal) =>
      runComparison(connectionId, settings, { baseUrl: apiUrl, signal });
// Lists the backend's real connections for the selector (#76); null keeps
// the selector on the bundled fixture catalog, as before this endpoint.
const defaultConnectionCatalogLoader: ConnectionCatalogLoader | null = apiUrl === null
  ? null
  : createConnectionCatalogLoader(apiUrl);

// Lists the time-of-day presets on the Scenario setup screen (#261).
const defaultPresetLoader: PresetLoader | null = apiUrl === null
  ? null
  : createPresetLoader(apiUrl);

// Reads where each setting came from for the provenance badges (US-7.1).
const defaultParameterProvenanceLoader: ParameterProvenanceLoader | null = apiUrl === null
  ? null
  : createParameterProvenanceLoader(apiUrl);

interface AppProps {
  // Injectable for tests; null keeps the app on the mock catalog.
  runLoader?: ConnectionRunLoader | null;
  // Injectable for tests; null disables "Run scenario".
  scenarioRunner?: ScenarioRunner | null;
  // Injectable for tests; null keeps the selector on the bundled fixture catalog.
  connectionCatalogLoader?: ConnectionCatalogLoader | null;
  // Injectable for tests; null shows the Compare screen's "no API" note.
  comparisonRunner?: ComparisonRunner | null;
  // Injectable for tests; null leaves every provenance badge "Unspecified".
  parameterProvenanceLoader?: ParameterProvenanceLoader | null;
  // Injectable for tests; null hides the time-of-day preset picker.
  presetLoader?: PresetLoader | null;
}

export default function App({
  runLoader = defaultRunLoader,
  scenarioRunner = defaultScenarioRunner,
  comparisonRunner = defaultComparisonRunner,
  connectionCatalogLoader = defaultConnectionCatalogLoader,
  parameterProvenanceLoader = defaultParameterProvenanceLoader,
  presetLoader = defaultPresetLoader,
}: Readonly<AppProps>) {
  // Loaded once here and passed down, so every screen shows the same sources.
  const [provenance, setProvenance] = useState<ParameterProvenanceMap>({});
  // Time-of-day presets (#261), also loaded once: only the active screen is
  // mounted, so loading them in Scenario setup refetched on every visit.
  const [presets, setPresets] = useState<ScenarioPreset[]>([]);
  const [presetError, setPresetError] = useState<string | null>(null);
  // Leased by the shell so playback keeps its position across screen changes.
  useEffect(startPlaybackClock, []);
  const selectedConnectionId = usePlaybackStore((state) => state.selectedConnectionId);
  const activeView = useViewStore((state) => state.activeView);
  const setView = useViewStore((state) => state.setView);

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

  useEffect(() => {
    if (parameterProvenanceLoader === null) return;
    const controller = new AbortController();
    parameterProvenanceLoader(controller.signal)
      .then((entries) => {
        if (!controller.signal.aborted) {
          setProvenance(entries);
        }
      })
      .catch(() => {
        // Keep empty provenance map; panels handle missing entries gracefully.
      });
    return () => controller.abort();
  }, [parameterProvenanceLoader]);

  useEffect(() => {
    if (presetLoader === null) return;
    const controller = new AbortController();
    presetLoader(controller.signal)
      .then((loaded) => {
        if (!controller.signal.aborted) setPresets(loaded);
      })
      .catch((error: unknown) => {
        // Unmounting aborts the request; that is not a failure to report.
        if (controller.signal.aborted) return;
        setPresetError(error instanceof Error ? error.message : "Could not load presets.");
      });
    return () => controller.abort();
  }, [presetLoader]);

  // One entry per sidebar item; only the active one is mounted.
  const screens: Record<AppView, ReactNode> = {
    station: <StationView provenance={provenance} />,
    compare: <CompareView runner={comparisonRunner} />,
    results: <ResultsView />,
    setup: <SetupView runner={scenarioRunner} provenance={provenance}
      onShowSources={() => setView("sources")}
      presets={presets} presetError={presetError} />,
    sources: <SourcesView provenance={provenance} />,
  };

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand">
          <div className="brand-mark" aria-hidden="true">↔</div>
          <div className="brand-text">
            <strong>TransitSync</strong>
            <small>Metro-REM transfer coordination</small>
          </div>
        </div>
        <ConnectionSelector />
        {/* The connections come from the REM and STM GTFS feeds. Both are CC BY 4.0,
            so each badge carries the credit and links to its own feed (#313). */}
        <div className="schedule-sources">
          <ProvenanceBadge parameterKey="rem_schedule" label="REM schedule"
            provenance={provenance.rem_schedule} />
          <ProvenanceBadge parameterKey="stm_schedule" label="STM schedule"
            provenance={provenance.stm_schedule} />
        </div>
      </header>

      <div className="workspace">
        {/* Plain buttons, not links: there is no router, and the current
            screen is marked with aria-current so screen readers announce it. */}
        <nav className="sidebar" aria-label="Workspace">
          <div className="section-label">Workspace</div>
          {VIEWS.map((view) => (
            <button key={view.id} type="button" className="nav-item"
              aria-current={view.id === activeView ? "page" : undefined}
              onClick={() => setView(view.id)}>
              {view.label}
            </button>
          ))}
        </nav>

        {/* Each screen has its own grid, since only the station view needs
            the map, inspector and playback rows. */}
        <main className={`content content--${activeView}`}>
          {screens[activeView]}
        </main>
      </div>
    </div>
  );
}
