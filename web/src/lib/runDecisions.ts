// AI contribution: 50% or more AI-generated
/**
 * Hold decisions recorded by a simulated run, for the decision view (#57),
 * and what the strategy saw at each of them (#39).
 *
 * The run endpoint returns the strategy's holds in `decisions` and the
 * seen-versus-true values behind them in `estimates` (api/station_view.py),
 * so each strategy shows its own list, No control shows none, and the gaps
 * grow with the error magnitude. Mock runs have neither key; they get null
 * so the caller can fall back to its illustrative fixture. Records are read
 * defensively, like mode switches: a malformed one is skipped instead of
 * breaking playback.
 */
import type { EstimatesRecord, HoldDecisionRecord, SeenAndTrue } from "../types/decision";

/** True for a finite number, the only usable kind of time or duration. */
function isFiniteNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

/** The run's list under `key`, or null when the run has no such list. */
function runList(run: unknown, key: string): unknown[] | null {
  if (typeof run !== "object" || run === null) return null;
  const list = (run as Record<string, unknown>)[key];
  return Array.isArray(list) ? list : null;
}

/** Keep the entries that `read` accepts, dropping the rest. */
function readEach<T>(entries: unknown[], read: (entry: unknown) => T | null): T[] {
  return entries.flatMap((entry) => {
    const value = read(entry);
    return value === null ? [] : [value];
  });
}

/** A field read as an object, or null when it is not one. */
function asRecord(value: unknown): Record<string, unknown> | null {
  return typeof value === "object" && value !== null ? (value as Record<string, unknown>) : null;
}

/** A seen and true pair; each side is a finite number or null (nothing to predict). */
function toSeenTrue(value: unknown): SeenAndTrue | null {
  const pair = asRecord(value);
  const usable = (side: unknown) => side === null || isFiniteNumber(side);
  if (pair === null || !usable(pair.seen) || !usable(pair.true)) return null;
  return { seen: pair.seen as number | null, true: pair.true as number | null };
}

/** One estimated train: its arrival and load as seen and true. */
function toEstimatedTrain(entry: unknown): EstimatesRecord["trains"][number] | null {
  const train = asRecord(entry);
  if (train === null || typeof train.train_id !== "string") return null;
  const predicted_arrival_s = toSeenTrue(train.predicted_arrival_s);
  const onboard_load = toSeenTrue(train.onboard_load);
  if (predicted_arrival_s === null || onboard_load === null) return null;
  return { train_id: train.train_id, predicted_arrival_s, onboard_load };
}

/** One estimated transfer group: still walking and total size, seen and true. */
function toEstimatedTransfer(entry: unknown): EstimatesRecord["transfers"][number] | null {
  const group = asRecord(entry);
  if (group === null || typeof group.group_id !== "string") return null;
  const passenger_count = toSeenTrue(group.passenger_count);
  const group_size = toSeenTrue(group.group_size);
  if (passenger_count === null || group_size === null) return null;
  return { group_id: group.group_id, passenger_count, group_size };
}

/** One estimates record; null unless it can be matched to a decision. */
function toEstimates(entry: unknown): EstimatesRecord | null {
  const record = asRecord(entry);
  if (record === null || !isFiniteNumber(record.time_s)) return null;
  const { train_id, station_id, platform_id, trains, transfers } = record;
  if (typeof train_id !== "string" || typeof platform_id !== "string") return null;
  if (typeof station_id !== "string") return null;
  return {
    time_s: record.time_s,
    train_id,
    station_id,
    platform_id,
    trains: Array.isArray(trains) ? readEach(trains, toEstimatedTrain) : [],
    transfers: Array.isArray(transfers) ? readEach(transfers, toEstimatedTransfer) : [],
  };
}

/**
 * The run's estimates, or null when it carries no `estimates` list (mock
 * playback). An empty list means no shown decision had any.
 */
export function runEstimates(run: unknown): EstimatesRecord[] | null {
  const estimates = runList(run, "estimates");
  return estimates === null ? null : readEach(estimates, toEstimates);
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
  const decisions = runList(run, "decisions");
  if (decisions === null) return null;
  return readEach(decisions, toDecision).toSorted((a, b) => a.time_s - b.time_s);
}
