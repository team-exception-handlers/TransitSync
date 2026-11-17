// AI contribution: 50% or more AI-generated
/** Reading the operating rules a simulated run used (US-2.5, #57). */
import { describe, expect, it } from "vitest";
import { runOperatingRules } from "../../src/lib/runOperatingRules";

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
