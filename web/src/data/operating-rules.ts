// AI contribution: 50% or more AI-generated
/**
 * Fixture mirroring simulator/control/settings.py OperatingRulesConfig
 * defaults (US-2.5, Task 2.5.1). No backend HTTP endpoint serves the active
 * scenario's operating rules yet; this fixture stands in until it exists.
 */
import type {
  OperatingRule,
  OperatingRulesConfig,
  RuleName,
} from "../types/operatingRules";

export const operatingRulesConfig: OperatingRulesConfig = {
  max_hold_time: 300,
  min_safe_gap: 60,
  rule_action_map: {
    max_hold_exceeded: "CLAMP",
    headway_violation: "REFUSE",
    one_hop_violation: "REFUSE",
  },
};

const RULE_DESCRIPTIONS: Record<RuleName, string> = {
  max_hold_exceeded:
    `Requested hold exceeds the maximum hold time of ${operatingRulesConfig.max_hold_time}s`,
  headway_violation:
    `Hold would leave less than the minimum safe gap of ${operatingRulesConfig.min_safe_gap}s between trains`,
  one_hop_violation:
    "Target train for the connection is already system-delayed (one-hop constraint)",
};

export const operatingRules: OperatingRule[] = (
  Object.keys(operatingRulesConfig.rule_action_map) as RuleName[]
).map((name) => ({
  name,
  action: operatingRulesConfig.rule_action_map[name],
  description: RULE_DESCRIPTIONS[name],
}));
