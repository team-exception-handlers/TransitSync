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
  RuleCheck,
  RuleName,
  RuleViolation,
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

/** One reported violation, or null when a field is missing or the wrong type. */
function toViolation(entry: unknown): RuleViolation | null {
  if (typeof entry !== "object" || entry === null) return null;
  const { rule, time_s, subject_id, message } = entry as Record<string, unknown>;
  if (rule !== "max_hold_exceeded" && rule !== "headway_violation") return null;
  if (!isFiniteNumber(time_s) || typeof subject_id !== "string") return null;
  if (typeof message !== "string") return null;
  return { rule, time_s, subject_id, message };
}

/**
 * The run's post-run rule check (#400), or null when the run has none (mock
 * playback, or a cached response from before the check existed). Malformed
 * violations are skipped; `passed` still decides whether the run failed.
 */
export function runRuleCheck(run: unknown): RuleCheck | null {
  if (typeof run !== "object" || run === null) return null;
  const { rule_check } = run as Record<string, unknown>;
  if (typeof rule_check !== "object" || rule_check === null) return null;
  const { passed, violations } = rule_check as Record<string, unknown>;
  if (typeof passed !== "boolean" || !Array.isArray(violations)) return null;
  return {
    passed,
    violations: violations.flatMap((entry: unknown) => {
      const violation = toViolation(entry);
      return violation === null ? [] : [violation];
    }),
  };
}
