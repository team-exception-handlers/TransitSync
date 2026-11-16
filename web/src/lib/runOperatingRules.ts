// AI contribution: 50% or more AI-generated
/**
 * The operating rules a simulated run used, for the operating rules panel
 * (US-2.5, #57).
 *
 * The run endpoint returns the active limits in `operating_rules` and the
 * described rules in `rules` (api/station_view.py), so the panel shows the
 * maximum hold the user picked instead of the 300 s default. Mock runs have
 * neither key; they get null so the panel can fall back to its fixture. A
 * malformed rule entry is skipped; malformed limits give null, because a
 * panel showing half the run's rules and half the fixture's would mislead.
 */
import type {
  OperatingRule,
  OperatingRulesConfig,
  RuleAction,
  RuleName,
} from "../types/operatingRules";

/** The run's limits and its rules in display order. */
export interface RunOperatingRules {
  config: OperatingRulesConfig;
  rules: OperatingRule[];
}

const RULE_NAMES: readonly RuleName[] = [
  "max_hold_exceeded",
  "headway_violation",
  "one_hop_violation",
];

/** True for a finite number of seconds. */
function isFiniteNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

/** True for one of the two actions a rule can take. */
function isAction(value: unknown): value is RuleAction {
  return value === "CLAMP" || value === "REFUSE";
}

/** True for a rule name the panel knows how to label. */
function isRuleName(value: unknown): value is RuleName {
  return RULE_NAMES.includes(value as RuleName);
}

/** The run's limits, or null unless every limit and rule action is usable. */
function toConfig(value: unknown): OperatingRulesConfig | null {
  if (typeof value !== "object" || value === null) return null;
  const { max_hold_time, min_safe_gap, rule_action_map } = value as Record<string, unknown>;
  if (!isFiniteNumber(max_hold_time) || !isFiniteNumber(min_safe_gap)) return null;
  if (typeof rule_action_map !== "object" || rule_action_map === null) return null;
  const actions = rule_action_map as Record<string, unknown>;
  if (!RULE_NAMES.every((name) => isAction(actions[name]))) return null;
  return {
    max_hold_time,
    min_safe_gap,
    rule_action_map: actions as Record<RuleName, RuleAction>,
  };
}

/** One described rule, or null when its name, action or text is unusable. */
function toRule(entry: unknown): OperatingRule | null {
  if (typeof entry !== "object" || entry === null) return null;
  const { name, action, description } = entry as Record<string, unknown>;
  if (!isRuleName(name) || !isAction(action) || typeof description !== "string") return null;
  return { name, action, description };
}

/** The run's operating rules, or null for a run without usable limits (mock). */
export function runOperatingRules(run: unknown): RunOperatingRules | null {
  if (typeof run !== "object" || run === null) return null;
  const { operating_rules, rules } = run as Record<string, unknown>;
  const config = toConfig(operating_rules);
  if (config === null) return null;
  const described = Array.isArray(rules) ? rules : [];
  return {
    config,
    rules: described.flatMap((entry: unknown) => {
      const rule = toRule(entry);
      return rule === null ? [] : [rule];
    }),
  };
}
