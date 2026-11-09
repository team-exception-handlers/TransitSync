// AI contribution: 50% or more AI-generated
/**
 * Fixture hold decisions mirroring simulator/control/decision.py
 * HoldDecision and the Hold event (simulator/engine/events.py), for US-2.5
 * Task 2.5.2. No backend HTTP endpoint serves recorded decisions for a run
 * yet; this fixture stands in until it exists.
 */
import type {
  EstimatesRecord,
  HoldDecisionRecord,
  SeenAndTrue,
} from "../types/decision";

export const decisionRecords: HoldDecisionRecord[] = [
  {
    time_s: 120,
    train_id: "T-101",
    station_id: "32",
    platform_id: "green_mcgill_0",
    requested_s: 45,
    applied_s: 45,
    reason: "hold for transfer group G-12",
  },
  {
    time_s: 240,
    train_id: "T-204",
    station_id: "32",
    platform_id: "green_mcgill_0",
    requested_s: 420,
    applied_s: 300,
    reason: "hold for transfer group G-30 (clamped to max_hold_time 300 s)",
  },
  {
    time_s: 300,
    train_id: "T-317",
    station_id: "32",
    platform_id: "green_mcgill_0",
    requested_s: 90,
    applied_s: 0,
    reason:
      "refused: one-hop constraint violation (train already system-delayed)",
  },
];

/** A seen and true pair, in the shape of the backend record. */
const seenTrue = (seen: number | null, actual: number | null) => ({
  seen,
  true: actual,
});
/** A train's estimated arrival in seconds and its onboard load. */
const train = (train_id: string, arrival: SeenAndTrue, load: SeenAndTrue) => ({
  train_id,
  predicted_arrival_s: arrival,
  onboard_load: load,
});
/** A transfer group's still-walking count and its size. */
const group = (group_id: string, walking: SeenAndTrue, size: SeenAndTrue) => ({
  group_id,
  passenger_count: walking,
  group_size: size,
});
// REM trains feed the green-line trains (T-) held at McGill above
/** An estimates record at the McGill green-line platform used above. */
const atMcGill = (
  time_s: number,
  train_id: string,
  trains: EstimatesRecord["trains"],
  transfers: EstimatesRecord["transfers"],
): EstimatesRecord => ({
  time_s,
  train_id,
  station_id: "32",
  platform_id: "green_mcgill_0",
  trains,
  transfers,
});

/**
 * Estimates records for the decisions above, cut down to the feeder train and
 * its transfer group. Arrival gaps are about one sigma(tau) at kappa = 1
 * (Mathematical Foundations section 7); REM-09 has no next stop.
 */
export const estimateRecords: EstimatesRecord[] = [
  // Held for G-12, but REM-12 looks 16 s later than it really is
  atMcGill(
    120,
    "T-101",
    [train("REM-12", seenTrue(181, 165), seenTrue(352, 320))],
    [group("G-12", seenTrue(38, 42), seenTrue(54, 60))],
  ),
  // One draw scales both counts of a group, so both are off by the same share
  atMcGill(
    240,
    "T-204",
    [train("REM-14", seenTrue(262, 300), seenTrue(410, 455))],
    [group("G-30", seenTrue(70, 64), seenTrue(88, 80))],
  ),
  // REM-09 ends its trip here, so only its load is estimated
  atMcGill(300, "T-317", [train("REM-09", seenTrue(null, null), seenTrue(290, 300))], []),
];
