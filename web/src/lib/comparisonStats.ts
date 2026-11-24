// AI contribution: 50% or more AI-generated
/**
 * Running totals for one Compare panel (US-4.1). Pure, so a backwards seek
 * gives exact totals again. Also each side's whole-run time saved and lost
 * against the other side (US-4.3).
 */
import type { PassengerOutcome, StationViewData } from "../types/stationView";
import type { PassengerSplit } from "./simulation-api";

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

/**
 * Both sides' changes from the API's split (#285). What holding saved a
 * passenger, no holding cost them, so the no-holding side is the mirror image.
 */
export function timeChanges(split: PassengerSplit): { holding: TimeChange; noHolding: TimeChange } {
  const holding = {
    saved_s: split.total_time_saved_s, savedPassengers: split.better_off,
    lost_s: split.total_time_lost_s, lostPassengers: split.worse_off,
  };
  const noHolding = {
    saved_s: holding.lost_s, savedPassengers: holding.lostPassengers,
    lost_s: holding.saved_s, lostPassengers: holding.savedPassengers,
  };
  return { holding, noHolding };
}

/** Round to whole seconds and show as "45 s", "4 min 15 s" or "3 h 11 min". */
export function formatDuration(seconds: number): string {
  const total = Math.round(seconds);
  if (total < 60) return `${total} s`;
  if (total < 3600) return `${Math.floor(total / 60)} min ${total % 60} s`;
  return `${Math.floor(total / 3600)} h ${Math.floor((total % 3600) / 60)} min`;
}
