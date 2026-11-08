// AI contribution: 50% or more AI-generated
/**
 * Fixture hold decisions mirroring simulator/control/decision.py
 * HoldDecision and the Hold event (simulator/engine/events.py), for US-2.5
 * Task 2.5.2. No backend HTTP endpoint serves recorded decisions for a run
 * yet; this fixture stands in until it exists.
 */
import type { HoldDecisionRecord } from "../types/decision";

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
