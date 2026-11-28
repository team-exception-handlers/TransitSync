// AI contribution: 50% or more AI-generated
/**
 * Where the followed passenger is in one run at a moment of playback, and how
 * their connection has turned out so far (US-4.2, #239). Pure, so a backwards
 * seek gives the exact state again. An outcome shows only once it happens:
 * "made" when their train leaves with them, "missed" when one leaves without.
 */
import { missedAt } from "./comparisonStats";
import type {
  PassengerOutcome, PassengerPhase, PassengerTrack, StationViewData,
} from "../types/stationView";

/** "absent": not in this run; "arriving": still on the train they transfer from. */
export type Whereabouts =
  | "absent"
  | "arriving"
  | Exclude<PassengerPhase, "boarded">
  | "onboard"
  | "left";

/** The connection so far; a miss names the train that left without them. */
export type ConnectionOutcome =
  | { kind: "open" }
  | { kind: "made" }
  | { kind: "missed"; trainId: string; delay_s: number | null };

/** The followed passenger's state in one run at one moment. */
export interface JourneyNow {
  where: Whereabouts;
  connectionLabel: string | null;
  trainId: string | null;
  outcome: ConnectionOutcome;
}

const OPEN: ConnectionOutcome = { kind: "open" };
const ABSENT: JourneyNow = { where: "absent", connectionLabel: null, trainId: null, outcome: OPEN };

/** Phase of the track's latest sample at `time_s`; before the first one they have not alighted. */
function phaseAt(track: PassengerTrack | undefined, time_s: number): Whereabouts {
  const sample = track?.samples.findLast((item) => item.time_s <= time_s);
  if (sample === undefined) return "arriving";
  // Mock runs have no outcomes, so a "boarded" sample is all they say
  return sample.phase === "boarded" ? "onboard" : sample.phase;
}

/**
 * The outcome once it has happened. It checks `status` as the panel's counts
 * do, so the readout and the panel can never give different answers.
 */
function outcomeAt(
  run: StationViewData, outcome: PassengerOutcome | undefined, time_s: number, left: boolean,
): ConnectionOutcome {
  if (outcome?.status === "made") return left ? { kind: "made" } : OPEN;
  if (outcome?.status !== "missed") return OPEN;
  const miss = missedAt(run, outcome);
  if (miss === null || miss.time_s > time_s) return OPEN;
  // Someone who missed a train and left on a later one still missed
  return { kind: "missed", trainId: miss.trainId, delay_s: left ? outcome.delay_s : null };
}

/**
 * The followed passenger in `run` at `time_s`. The outcome's boarding and
 * departure times win over the track, because a passenger who missed a train
 * keeps a "missed" track sample even after boarding a later one.
 */
export function journeyAt(run: StationViewData, passengerId: string, time_s: number): JourneyNow {
  const track = run.passenger_tracks.find((item) => item.passenger_id === passengerId);
  const outcome = run.passenger_outcomes?.find((item) => item.passenger_id === passengerId);
  if (track === undefined && outcome === undefined) return ABSENT;

  const connectionId = track?.connection_id ?? outcome?.connection_id;
  const label = run.connections.find((item) => item.id === connectionId)?.label ?? null;
  const boarded = outcome?.boarding_s != null && outcome.boarding_s <= time_s;
  const left = outcome?.departure_s != null && outcome.departure_s <= time_s;

  let where = phaseAt(track, time_s);
  if (left) where = "left";
  else if (boarded) where = "onboard";
  return {
    where,
    connectionLabel: label,
    trainId: boarded ? (outcome?.boarded_train_id ?? null) : null,
    outcome: outcomeAt(run, outcome, time_s, left),
  };
}
