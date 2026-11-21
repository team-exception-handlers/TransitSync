// AI contribution: 50% or more AI-generated
// @vitest-environment jsdom
/** The active operating-rule set renders with its values and clamp/refuse actions. */
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { OperatingRulesPanel } from "../../src/components/operating-rules-panel";
import { operatingRulesConfig } from "../../src/data/operating-rules";
import { stationViewData } from "../../src/data/stationViewData";
import { formatTime } from "../../src/lib/time";
import { usePlaybackStore } from "../../src/store/usePlaybackStore";

describe("OperatingRulesPanel", () => {
  afterEach(() => {
    cleanup();
  });

  it("renders the active rule set's configured values", () => {
    render(<OperatingRulesPanel />);

    expect(
      screen.getByText(`${operatingRulesConfig.max_hold_time}s`)
    ).toBeDefined();
    expect(
      screen.getByText(`${operatingRulesConfig.min_safe_gap}s`)
    ).toBeDefined();
  });

  it("renders every configured rule by name", () => {
    render(<OperatingRulesPanel />);

    for (const name of Object.keys(operatingRulesConfig.rule_action_map)) {
      expect(screen.getByText(name)).toBeDefined();
    }
  });

  it("clarifies which settings are not enforced by the simulator", () => {
    render(<OperatingRulesPanel />);
    expect(screen.getByText("Not enforced yet")).toBeDefined();
    expect(screen.getByText("headway_violation").closest("li")?.textContent)
      .toContain("headway checking is not enforced yet");
    expect(screen.getByText("one_hop_violation").closest("li")?.textContent)
      .toContain("Always refuses; the configured action is not used yet");
  });

  it("distinguishes clamping rules from refusing rules", () => {
    render(<OperatingRulesPanel />);

    for (const [name, action] of Object.entries(
      operatingRulesConfig.rule_action_map
    )) {
      const row = screen.getByText(name).closest("li");
      expect(row).not.toBeNull();
      expect(row?.className).toContain(`operating-rule--${action.toLowerCase()}`);
      expect(row?.querySelector("[data-action]")?.getAttribute("data-action")).toBe(
        action
      );
    }

    // At least one of each action must be present for the distinction to be
    // observable at all (defaults mix CLAMP and REFUSE).
    const actions = Object.values(operatingRulesConfig.rule_action_map);
    expect(actions).toContain("CLAMP");
    expect(actions).toContain("REFUSE");
  });
});

/** Rules as the run endpoint returns them for a 60 s maximum hold. */
const runRules = {
  operating_rules: {
    max_hold_time: 60,
    min_safe_gap: 60,
    rule_action_map: {
      max_hold_exceeded: "CLAMP",
      headway_violation: "REFUSE",
      one_hop_violation: "REFUSE",
    },
  },
  rules: [
    {
      name: "max_hold_exceeded",
      action: "CLAMP",
      description: "Requested hold exceeds the maximum hold time of 60s",
    },
  ],
};

describe("OperatingRulesPanel with a simulated run", () => {
  afterEach(() => {
    cleanup();
    // Back to mock playback, which has no rules of its own
    usePlaybackStore.getState().loadData(stationViewData);
  });

  it("shows the maximum hold the run used instead of the 300 s default", () => {
    usePlaybackStore.getState().loadData({ ...stationViewData, ...runRules });
    render(<OperatingRulesPanel />);

    expect(screen.getAllByText("60s")).toHaveLength(2);
    expect(screen.queryByText("300s")).toBeNull();
    expect(screen.getByText(runRules.rules[0].description)).toBeDefined();
  });

  it("falls back to the fixture when the run's limits are unusable", () => {
    const broken = { ...runRules.operating_rules, max_hold_time: "60" };
    usePlaybackStore.getState().loadData({ ...stationViewData, ...runRules, operating_rules: broken });
    render(<OperatingRulesPanel />);

    expect(screen.getByText(`${operatingRulesConfig.max_hold_time}s`)).toBeDefined();
  });

  it("renders provenance badge for min_safe_gap when provided", () => {
    render(
      <OperatingRulesPanel
        provenance={{
          min_safe_gap: {
            classification: "estimated",
            source_name: "TransitSync Operational Thresholds",
            source_link: "",
          },
        }}
      />,
    );

    const badge = screen.getByTestId("provenance-min_safe_gap");
    expect(badge.textContent).toContain("Estimated");
    expect(badge.textContent).toContain("TransitSync Operational Thresholds");
  });
});

describe("OperatingRulesPanel rule check (#400)", () => {
  afterEach(() => {
    cleanup();
    usePlaybackStore.getState().loadData(stationViewData);
  });

  it("says the run passed when no rule was broken", () => {
    usePlaybackStore.getState().loadData({
      ...stationViewData, ...runRules, rule_check: { passed: true, violations: [] },
    });
    render(<OperatingRulesPanel />);

    expect(screen.getByText("Rule check: passed, no rule broken in this run")).toBeDefined();
  });

  it("lists every violation when the run broke a rule", () => {
    const messages = [
      "Max Hold Violation: Train T1 at t=900.0s applied hold of 150.0s exceeds max 60.0s.",
      "Min Safe Gap Violation: Platform P1 gap 59.0s < minimum 60.0s.",
    ];
    const violations = [
      { rule: "max_hold_exceeded", time_s: 900, subject_id: "T1", message: messages[0] },
      { rule: "headway_violation", time_s: 959, subject_id: "P1", message: messages[1] },
    ];
    usePlaybackStore.getState().loadData({
      ...stationViewData, ...runRules, rule_check: { passed: false, violations },
    });
    render(<OperatingRulesPanel />);

    expect(screen.getByText("Rule check: failed, 2 violations")).toBeDefined();
    // Times are clock times (start_clock_s + time_s), like the clock and timeline
    const start = stationViewData.start_clock_s;
    const first = screen.getByText(
      `${formatTime(900, start)}: Train T1 held longer than the max hold time`,
    );
    expect(first.getAttribute("title")).toBe(messages[0]);
    expect(
      screen.getByText(`${formatTime(959, start)}: Platform P1 departures closer than the min safe gap`),
    ).toBeDefined();
  });

  it("says details are unavailable when a failed check has no usable violations", () => {
    const malformed = [{ rule: "max_hold_exceeded", time_s: "900", subject_id: "T1", message: "x" }];
    usePlaybackStore.getState().loadData({
      ...stationViewData, ...runRules, rule_check: { passed: false, violations: malformed },
    });
    render(<OperatingRulesPanel />);

    expect(screen.getByText("Rule check: failed (details unavailable)")).toBeDefined();
    expect(screen.queryByText(/0 violations/)).toBeNull();
  });

  it("shows no rule check for mock playback", () => {
    render(<OperatingRulesPanel />);

    expect(screen.queryByText(/Rule check:/)).toBeNull();
  });
});
