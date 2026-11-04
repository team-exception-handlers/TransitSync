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
    station_id: "berri-uqam",
    platform_id: "berri-uqam-orange-eastbound",
    requested_s: 45,
    applied_s: 45,
    reason: "hold for transfer group G-12",
  },
  {
    time_s: 340,
    train_id: "T-204",
    station_id: "lionel-groulx",
    platform_id: "lionel-groulx-green-westbound",
    requested_s: 420,
    applied_s: 300,
    reason: "hold for transfer group G-30 (clamped to max_hold_time 300 s)",
  },
  {
    time_s: 610,
    train_id: "T-317",
    station_id: "snowdon",
    platform_id: "snowdon-blue-eastbound",
    requested_s: 90,
    applied_s: 0,
    reason:
      "refused: one-hop constraint violation (train already system-delayed)",
  },
];
