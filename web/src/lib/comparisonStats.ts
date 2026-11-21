// AI contribution: 50% or more AI-generated
/**
 * Running totals for one Compare panel (US-4.1). Pure, so a backwards seek
 * gives exact totals again.
 */
import type { StationViewData } from "../types/stationView";

/** What a panel shows about holding at one moment of its run. */
export interface ComparisonStats {
  holdingNow: boolean;
  /** Holds started so far. */
  holds: number;
  /** Transfers whose train has left with them on board, on time or late. */
  made: number;
  missed: number;
}

/**
 * Count holds and connection outcomes at `time_s` (seconds since run start).
 * A hold is active for `applied_s` seconds from its start, and a passenger
 * counts once their train departs. Mock runs without these fields count zero.
 */
export function comparisonStatsAt(run: StationViewData, time_s: number): ComparisonStats {
  const holdEvents = run.time_series?.hold_events ?? [];
  const started = holdEvents.filter((hold) => hold.time_s <= time_s);
  const holdingNow = started.some((hold) => time_s < hold.time_s + hold.applied_s);
  let made = 0;
  let missed = 0;
  for (const outcome of run.passenger_outcomes ?? []) {
    if (outcome.departure_s === null || outcome.departure_s > time_s) continue;
    if (outcome.status === "made") made += 1;
    else if (outcome.status === "missed") missed += 1;
  }
  return { holdingNow, holds: started.length, made, missed };
}
