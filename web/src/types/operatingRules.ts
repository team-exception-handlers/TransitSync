// AI contribution: 50% or more AI-generated
/**
 * Mirrors simulator/control/settings.py OperatingRulesConfig (US-2.4, US-2.5,
 * Task 2.5.1, #53, #57, #58). The backend has no HTTP endpoint for this yet;
 * see web/src/data/operating-rules.ts for the fixture pending it.
 */

/** What an operating rule does when its condition is triggered. */
export type RuleAction = "CLAMP" | "REFUSE";

/** Rule names recognized by OperatingRulesConfig.rule_action_map. */
export type RuleName =
  | "max_hold_exceeded"
  | "headway_violation"
  | "one_hop_violation";

/** One operating rule as configured for the active scenario. */
export interface OperatingRule {
  name: RuleName;
  action: RuleAction;
  /** Human-readable description of what triggers this rule. */
  description: string;
}

/** Mirrors OperatingRulesConfig.to_dict() exactly: field names and shape. */
export interface OperatingRulesConfig {
  max_hold_time: number;
  min_safe_gap: number;
  rule_action_map: Record<RuleName, RuleAction>;
}
