// AI contribution: 50% or more AI-generated
/**
 * Running totals for one Compare panel (US-4.1), and each side's time saved
 * and lost against the other side so far (US-4.3). Pure, so a backwards seek
 * gives exact totals again.
 */
import type { PassengerOutcome, StationViewData } from "../types/stationView";

/** What a panel shows about holding at one moment of its run. */
export interface ComparisonStats {
  holdingNow: boolean;
  /** Holds started so far. */
  holds: number;
  /** Transfers whose train has left with them on board, on time or late. */
  made: number;
  /** Transfers whose first possible train has left without them. */
  missed: number;
}

/** Key for one train at one platform; a train can visit several platforms. */
const visitKey = (trainId: string, platformId: string) => `${trainId}|${platformId}`;

/** Departure times of each train at each platform, in time order. */
function departuresByVisit(run: StationViewData): Map<string, number[]> {
  const visits = new Map<string, number[]>();
  for (const event of run.train_events) {
    if (event.event_type !== "train_departure") continue;
    const key = visitKey(event.train_id, event.platform_id);
    const times = visits.get(key) ?? [];
    times.push(event.time_s);
    visits.set(key, times);
  }
  for (const times of visits.values()) times.sort((a, b) => a - b);
  return visits;
}

/**
 * When the passenger's first missed train left the transfer platform. The
 * miss can happen while they are still walking, so the search starts at
 * alighting. Null when the run has no matching departure (mock data).
 */
function firstMissAt(
  outcome: PassengerOutcome,
  toPlatform: Map<string, string>,
  departures: Map<string, number[]>,
): number | null {
  const trainId = outcome.missed_train_ids[0];
  const platformId = toPlatform.get(outcome.connection_id);
  if (trainId === undefined || platformId === undefined) return null;
  const times = departures.get(visitKey(trainId, platformId)) ?? [];
  return times.find((time) => time >= outcome.alighting_s) ?? null;
}

/**
 * Count holds and connection outcomes at `time_s` (seconds since run start).
 * A hold is active for `applied_s` seconds from its start. A made connection
 * counts once the passenger's train departs. A missed one counts once the
 * first train they missed departs, whether or not they board a later one
 * before the run ends. Mock runs without these fields count zero.
 */
export function comparisonStatsAt(run: StationViewData, time_s: number): ComparisonStats {
  const holdEvents = run.time_series?.hold_events ?? [];
  const started = holdEvents.filter((hold) => hold.time_s <= time_s);
  const holdingNow = started.some((hold) => time_s < hold.time_s + hold.applied_s);
  // The platform each connection transfers to, where its misses are observed.
  const toPlatform = new Map(run.connections.map((item) => [item.id, item.to_platform_id]));
  const departures = departuresByVisit(run);
  let made = 0;
  let missed = 0;
  for (const outcome of run.passenger_outcomes ?? []) {
    if (outcome.status === "made") {
      if (outcome.departure_s !== null && outcome.departure_s <= time_s) made += 1;
    } else if (outcome.status === "missed") {
      const missAt = firstMissAt(outcome, toPlatform, departures);
      if (missAt !== null && missAt <= time_s) missed += 1;
    }
  }
  return { holdingNow, holds: started.length, made, missed };
}

/** Time one side saved and lost passengers against the other run (US-4.3). */
export interface TimeChange {
  saved_s: number;
  savedPassengers: number;
  lost_s: number;
  lostPassengers: number;
}

/** Both runs of a comparison and the API's unaffected threshold, in seconds. */
export interface ComparedPair {
  holding: StationViewData;
  noHolding: StationViewData;
  threshold_s: number;
}

/** The passenger split of both runs at one moment of playback. */
export interface SplitSoFar {
  holding: TimeChange;
  /** The mirror image: what holding saved a passenger, no holding cost them. */
  noHolding: TimeChange;
  unaffected: number;
  /** Not left in either run yet, or in one run only. */
  notCompared: number;
  /** Sum of every compared passenger's D; negative means holding saved time. */
  net_s: number;
}

/** When the passenger left, if that has happened by `time_s`. */
const leftBy = (outcome: PassengerOutcome | undefined, time_s: number) =>
  outcome?.departure_s != null && outcome.departure_s <= time_s ? outcome.departure_s : null;

const sum = (values: number[]) => values.reduce((total, value) => total + value, 0);

/**
 * The API's passenger split (#284) as it stands at `time_s`, so the scores
 * build up during playback (US-4.3). Same rule as the API: D is the departure
 * with holding minus the one without, `time_s` stands in for a run they have
 * not left yet, and |D| up to the threshold is unaffected. At the run end
 * this gives the API's split.
 */
export function splitAt({ holding, noHolding, threshold_s }: ComparedPair, time_s: number): SplitSoFar {
  const baseline = new Map((noHolding.passenger_outcomes ?? []).map((item) => [item.passenger_id, item]));
  const held = holding.passenger_outcomes ?? [];
  const saved: number[] = [];
  const lost: number[] = [];
  let unaffected = 0;
  // Every compared D, unaffected ones too, so small changes are not hidden
  let net_s = 0;
  for (const outcome of held) {
    const other = baseline.get(outcome.passenger_id);
    const heldAt = leftBy(outcome, time_s);
    const baselineAt = leftBy(other, time_s);
    // Missing from the other run, or gone from neither yet: nothing to compare
    if (other === undefined || (heldAt === null && baselineAt === null)) continue;
    const difference = (heldAt ?? time_s) - (baselineAt ?? time_s);
    net_s += difference;
    if (difference < -threshold_s) saved.push(-difference);
    else if (difference > threshold_s) lost.push(difference);
    else unaffected += 1;
  }
  const everyone = new Set([...held.map((item) => item.passenger_id), ...baseline.keys()]).size;
  const forHolding = {
    saved_s: sum(saved), savedPassengers: saved.length, lost_s: sum(lost), lostPassengers: lost.length,
  };
  return {
    holding: forHolding,
    noHolding: {
      saved_s: forHolding.lost_s, savedPassengers: forHolding.lostPassengers,
      lost_s: forHolding.saved_s, lostPassengers: forHolding.savedPassengers,
    },
    unaffected,
    notCompared: everyone - saved.length - lost.length - unaffected,
    net_s,
  };
}

/**
 * Show as "45 s", "4 min 15 s" or "3 h 12 min", rounding to the smallest
 * unit shown so every format rounds the same way (#244).
 */
export function formatDuration(seconds: number): string {
  const total = Math.round(seconds);
  if (total < 60) return `${total} s`;
  if (total < 3600) return `${Math.floor(total / 60)} min ${total % 60} s`;
  const minutes = Math.round(total / 60);
  return `${Math.floor(minutes / 60)} h ${minutes % 60} min`;
}
