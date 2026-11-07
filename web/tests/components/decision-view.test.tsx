// AI contribution: 50% or more AI-generated
// @vitest-environment jsdom
/** Refused and clamped decisions are marked distinctly from applied ones. */
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { DecisionView } from "../../src/components/decision-view";
import { decisionRecords } from "../../src/data/decisions";
import { decisionStatus } from "../../src/types/decision";

describe("DecisionView", () => {
  afterEach(() => {
    cleanup();
  });

  it("renders a row per decision marked with its status", () => {
    render(<DecisionView />);

    for (const decision of decisionRecords) {
      const status = decisionStatus(decision);
      const row = screen.getByText(decision.train_id).closest("li");
      expect(row).not.toBeNull();
      expect(row?.getAttribute("data-status")).toBe(status);
      expect(row?.className).toContain(`decision-row--${status}`);
    }
  });

  it("distinguishes refused and clamped decisions from each other and from applied ones", () => {
    render(<DecisionView />);

    const statuses = decisionRecords.map((decision) => decisionStatus(decision));
    expect(statuses).toContain("clamped");
    expect(statuses).toContain("refused");
    expect(statuses).toContain("applied");

    const clampedRow = screen
      .getByText(decisionRecords.find((d) => decisionStatus(d) === "clamped")!.train_id)
      .closest("li");
    const refusedRow = screen
      .getByText(decisionRecords.find((d) => decisionStatus(d) === "refused")!.train_id)
      .closest("li");
    const appliedRow = screen
      .getByText(decisionRecords.find((d) => decisionStatus(d) === "applied")!.train_id)
      .closest("li");

    expect(clampedRow?.className).not.toBe(refusedRow?.className);
    expect(clampedRow?.className).not.toBe(appliedRow?.className);
    expect(refusedRow?.className).not.toBe(appliedRow?.className);
  });

  it("shows the requested duration alongside the applied one for a clamped decision", () => {
    render(<DecisionView />);

    const clamped = decisionRecords.find((d) => decisionStatus(d) === "clamped");
    expect(clamped).toBeDefined();
    const row = screen.getByText(clamped!.train_id).closest("li");

    expect(row?.textContent).toContain(`requested ${clamped!.requested_s}s`);
    expect(row?.textContent).toContain(`applied ${clamped!.applied_s}s`);
  });

  it("shows the requested duration alongside the applied one for a refused decision", () => {
    render(<DecisionView />);

    const refused = decisionRecords.find((d) => decisionStatus(d) === "refused");
    expect(refused).toBeDefined();
    const row = screen.getByText(refused!.train_id).closest("li");

    expect(row?.textContent).toContain(`requested ${refused!.requested_s}s`);
    expect(row?.textContent).toContain(`applied ${refused!.applied_s}s`);
  });
});
