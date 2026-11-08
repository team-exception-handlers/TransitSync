// AI contribution: 50% or more AI-generated
// @vitest-environment jsdom
/** The active operating-rule set renders with its values and clamp/refuse actions. */
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { OperatingRulesPanel } from "../../src/components/operating-rules-panel";
import { operatingRulesConfig } from "../../src/data/operating-rules";

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
