// AI contribution: 50% or more AI-generated
/** Reading the operating rules a simulated run used (US-2.5, #57). */
import { describe, expect, it } from "vitest";
import { runOperatingRules, runRuleCheck } from "../../src/lib/runOperatingRules";

const limits = {
  max_hold_time: 45,
  min_safe_gap: 60,
  rule_action_map: {
    max_hold_exceeded: "REFUSE",
    headway_violation: "REFUSE",
    one_hop_violation: "REFUSE",
  },
};
const rule = {
  name: "max_hold_exceeded",
  action: "REFUSE",
  description: "Requested hold exceeds the maximum hold time of 45s",
};

describe("runOperatingRules", () => {
  it("returns the run's limits and rules, including a non-default action", () => {
    const result = runOperatingRules({ operating_rules: limits, rules: [rule] });

    expect(result?.config).toEqual(limits);
    expect(result?.rules).toEqual([rule]);
  });

  it("returns null for mock playback and for limits missing a rule action", () => {
    expect(runOperatingRules({ duration_s: 3600 })).toBeNull();
    const partial = { max_hold_exceeded: "CLAMP", headway_violation: "REFUSE" };
    expect(
      runOperatingRules({ operating_rules: { ...limits, rule_action_map: partial } }),
    ).toBeNull();
  });

  it("skips an unknown or malformed rule but keeps the valid ones", () => {
    const result = runOperatingRules({
      operating_rules: limits,
      rules: [rule, { ...rule, name: "speed_limit" }, { ...rule, action: "WARN" }, null],
    });

    expect(result?.rules).toEqual([rule]);
  });
});

/** A 150 s hold over a 120 s maximum, as the run endpoint reports it (#400). */
const violation = {
  rule: "max_hold_exceeded",
  time_s: 900,
  subject_id: "T1",
  message: "Max Hold Violation: Train T1 at t=900.0s applied hold of 150.0s exceeds max 120.0s.",
};

describe("runRuleCheck", () => {
  it("returns whether the run passed and each violation", () => {
    const check = runRuleCheck({ rule_check: { passed: false, violations: [violation] } });

    expect(check).toEqual({ passed: false, violations: [violation] });
  });

  it("returns null for mock playback and for a check without a boolean result", () => {
    expect(runRuleCheck({ duration_s: 3600 })).toBeNull();
    expect(runRuleCheck({ rule_check: null })).toBeNull();
    expect(runRuleCheck({ rule_check: { passed: "yes", violations: [] } })).toBeNull();
  });

  it("skips malformed violations but keeps the failed result", () => {
    const broken = [{ ...violation, rule: "one_hop_violation" }, { ...violation, time_s: "900" }];

    const check = runRuleCheck({ rule_check: { passed: false, violations: [...broken, violation] } });

    expect(check).toEqual({ passed: false, violations: [violation] });
  });
});
