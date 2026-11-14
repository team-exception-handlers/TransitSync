// AI contribution: 50% or more AI-generated
/**
 * Hold decisions recorded by a simulated run, for the decision view (#57).
 *
 * The run endpoint returns the strategy's holds in `decisions`
 * (HoldDecisionResponse in api/station_view.py), so each strategy shows its
 * own list and No control shows none. Mock runs have no such key; they get
 * null so the caller can fall back to its illustrative fixture. Records are
 * read defensively, like mode switches: a malformed one is skipped instead of
 * breaking playback.
 */
import type { HoldDecisionRecord } from "../types/decision";

/** True for a finite number, the only usable kind of time or duration. */
function isFiniteNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

/** Read one record; null unless every field the view prints is usable. */
function toDecision(record: unknown): HoldDecisionRecord | null {
  if (typeof record !== "object" || record === null) return null;
  const { time_s, train_id, station_id, platform_id, requested_s, applied_s, reason } =
    record as Record<string, unknown>;
  if (!isFiniteNumber(time_s) || !isFiniteNumber(requested_s) || !isFiniteNumber(applied_s)) {
    return null;
  }
  if (typeof train_id !== "string" || typeof station_id !== "string") return null;
  if (typeof platform_id !== "string" || typeof reason !== "string") return null;
  return { time_s, train_id, station_id, platform_id, requested_s, applied_s, reason };
}

/**
 * The run's decisions in time order, or null when the run carries no
 * `decisions` list at all (mock playback). An empty list is a real answer:
 * the strategy never held a train, as with No control.
 */
export function runDecisions(run: unknown): HoldDecisionRecord[] | null {
  if (typeof run !== "object" || run === null) return null;
  const { decisions } = run as { decisions?: unknown };
  if (!Array.isArray(decisions)) return null;
  const records = decisions.flatMap((record: unknown) => {
    const decision = toDecision(record);
    return decision === null ? [] : [decision];
  });
  return records.toSorted((a, b) => a.time_s - b.time_s);
}
