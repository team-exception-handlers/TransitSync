// AI contribution: 50% or more AI-generated
/**
 * Mirrors simulator/control/decision.py HoldDecision plus the train/station
 * context recorded on the Hold event (simulator/engine/events.py), for
 * US-2.5 Task 2.5.2, and the "estimates" record of decisions.jsonl (US-2.1,
 * #39). No HTTP endpoint serves these yet; see web/src/data/decisions.ts.
 */

/** Outcome of a hold decision once operating rules were applied. */
export type DecisionStatus = "applied" | "clamped" | "refused";

export interface HoldDecisionRecord {
  time_s: number;
  train_id: string;
  station_id: string;
  platform_id: string;
  /** Hold proposed by the strategy, in seconds (HoldDecision.requested_s). */
  requested_s: number;
  /** Hold actually applied after the safety rules, in seconds; never more
   * than requested_s (HoldDecision.applied_s). */
  applied_s: number;
  reason: string;
}

/**
 * Classify a decision from its requested/applied durations, matching
 * OperatingRulesEnforcer.validate: 0 applied means refused, a shorter
 * applied duration means clamped, otherwise the hold was applied unchanged.
 */
export function decisionStatus(decision: HoldDecisionRecord): DecisionStatus {
  if (decision.applied_s === 0) return "refused";
  if (decision.applied_s < decision.requested_s) return "clamped";
  return "applied";
}

/** Seen (with prediction error) and true value; null if nothing to predict. */
export interface SeenAndTrue {
  seen: number | null;
  true: number | null;
}

/** What the strategy saw next to the true values at one decision. */
export interface EstimatesRecord {
  time_s: number;
  train_id: string;
  station_id: string;
  platform_id: string;
  trains: {
    train_id: string;
    predicted_arrival_s: SeenAndTrue;
    onboard_load: SeenAndTrue;
  }[];
  transfers: {
    group_id: string;
    passenger_count: SeenAndTrue;
    group_size: SeenAndTrue;
  }[];
}

/** The estimates record of the same decision (time, train and platform). */
export function estimatesFor(
  decision: HoldDecisionRecord,
  records: EstimatesRecord[],
): EstimatesRecord | undefined {
  return records.find(
    (record) =>
      record.time_s === decision.time_s &&
      record.train_id === decision.train_id &&
      record.platform_id === decision.platform_id,
  );
}
