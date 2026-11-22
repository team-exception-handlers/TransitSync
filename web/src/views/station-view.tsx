// AI contribution: 50% or more AI-generated
/**
 * Station view screen (#408): the Canvas map with its heading, the clock,
 * operating rules and decisions, and the playback timeline.
 *
 * Moved out of `App.tsx` unchanged when the sidebar gained its other screens.
 * Every panel reads the run and playback position from `usePlaybackStore`, so
 * leaving this screen and coming back shows the same moment of the same run.
 */
import { DecisionView } from "../components/decision-view";
import { OperatingRulesPanel } from "../components/operating-rules-panel";
import { PlaybackControls } from "../components/playback-controls";
import { PlaybackTimeline } from "../components/PlaybackTimeline";
import { RunSummary } from "../components/run-summary";
import { SimulationClock } from "../components/simulation-clock";
import { SpeedSelector } from "../components/speed-selector";
import { StationCanvas } from "../components/station-canvas";
import { usePlaybackStore, type RunStatus } from "../store/usePlaybackStore";
import type { ParameterProvenanceMap } from "../types/provenance";

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

interface StationViewProps {
  /** Where each setting came from (US-7.1), for the rules and decision badges. */
  provenance?: ParameterProvenanceMap;
}

/** Lay out the station map, the right-hand panels and the playback bar. */
export function StationView({ provenance }: Readonly<StationViewProps>) {
  const runStatus = usePlaybackStore((state) => state.runStatus);
  const runError = usePlaybackStore((state) => state.runError);
  const data = usePlaybackStore((state) => state.data);
  const selectedConnectionId = usePlaybackStore((state) => state.selectedConnectionId);
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

  return (
    <>
      <section className="panel station-region" aria-label="Station view">
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

      {/* Right-hand panels: simulation time, operating rules, decisions. */}
      <aside className="inspector">
        <SimulationClock />
        <OperatingRulesPanel provenance={provenance} />
        <DecisionView provenance={provenance} />
      </aside>

      <section className="panel playback-region">
        <PlaybackControls />
        <PlaybackTimeline />
        <SpeedSelector />
      </section>
    </>
  );
}
