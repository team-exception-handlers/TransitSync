// AI contribution: 50% or more AI-generated
/**
 * The followed passenger on the Compare screen (US-4.2): who is followed and
 * how to stop (#238), and under each panel where they are, which train or
 * connection they are on and how their connection has turned out (#239).
 *
 * Reads only the shared playback time, so both panels' journeys move on the
 * same clock tick. The state itself comes from `journeyAt`.
 */
import { formatDuration } from "../lib/comparisonStats";
import { journeyAt, type JourneyNow, type Whereabouts } from "../lib/passengerJourney";
import { useComparisonStore } from "../store/useComparisonStore";
import { usePlaybackStore } from "../store/usePlaybackStore";
import type { StationViewData } from "../types/stationView";

// Plain words for each place, so the readout makes sense without the map.
const WHERE_TEXT: Record<Whereabouts, string> = {
  absent: "Not in this run",
  arriving: "Still on the arriving train",
  walking: "Walking the transfer corridor",
  queued: "Queued in the corridor",
  waiting: "Waiting on the platform",
  boarding: "Boarding",
  missed: "On the platform after a missed train",
  onboard: "On board, waiting to leave",
  left: "Left the station",
};

/** The train they are on, else the connection they are making. */
function trainText(journey: JourneyNow): string {
  if (journey.trainId) return `Train ${journey.trainId}`;
  return journey.connectionLabel ? `Transfer at ${journey.connectionLabel}` : "None";
}

/** The outcome so far, naming the missed train and the extra wait once known. */
function outcomeText({ where, outcome }: JourneyNow): string {
  if (where === "absent") return "Not in this run";
  if (outcome.kind === "open") return "Not decided yet";
  if (outcome.kind === "made") return "Made the connection";
  const missed = `Missed train ${outcome.trainId}`;
  return outcome.delay_s === null ? missed : `${missed}, left ${formatDuration(outcome.delay_s)} later`;
}

/** Where the followed passenger is in this panel's run; nothing when nobody is followed. */
export function PassengerJourney({ run }: Readonly<{ run: StationViewData }>) {
  const time = usePlaybackStore((state) => state.currentTime_s);
  const passengerId = useComparisonStore((state) => state.selectedPassengerId);
  if (passengerId === null) return null;
  const journey = journeyAt(run, passengerId, time);
  return (
    <dl className="comparison-stats-values passenger-journey" aria-label="Followed passenger">
      <div><dt>Where now</dt><dd>{WHERE_TEXT[journey.where]}</dd></div>
      <div><dt>Train or connection</dt><dd>{trainText(journey)}</dd></div>
      <div><dt>Connection outcome</dt><dd>{outcomeText(journey)}</dd></div>
    </dl>
  );
}

/**
 * Says who is followed in both panels, with a button to stop, or how to start
 * following someone. The button is the way to deselect without the canvas.
 */
export function FollowedPassengerBar() {
  const passengerId = useComparisonStore((state) => state.selectedPassengerId);
  const selectPassenger = useComparisonStore((state) => state.selectPassenger);
  if (passengerId === null) {
    return <p className="comparison-note">Click a passenger in either panel to follow them in both runs.</p>;
  }
  return (
    <p className="comparison-note followed-passenger">
      Following passenger <code>{passengerId}</code> in both runs.{" "}
      <button type="button" className="text-button" onClick={() => selectPassenger(null)}>
        Stop following
      </button>
    </p>
  );
}
