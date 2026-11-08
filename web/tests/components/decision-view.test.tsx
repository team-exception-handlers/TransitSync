// AI contribution: 50% or more AI-generated
// @vitest-environment jsdom
/** Refused and clamped decisions are marked distinctly from applied ones. */
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { act, cleanup, render, screen } from "@testing-library/react";
import { DecisionView } from "../../src/components/decision-view";
import { decisionRecords } from "../../src/data/decisions";
import { decisionStatus } from "../../src/types/decision";
import { stationViewData } from "../../src/data/stationViewData";
import { connectionRuns } from "../../src/data/connection-runs";
import { usePlaybackStore } from "../../src/store/usePlaybackStore";

describe("DecisionView", () => {
  beforeEach(() => {
    usePlaybackStore.getState().setAvailableRuns(connectionRuns);
    usePlaybackStore.getState().loadData(stationViewData);
    usePlaybackStore.getState().seek(stationViewData.duration_s);
  });
  afterEach(() => {
    cleanup();
  });

  it("reveals decisions at their timestamps and hides them again on rewind", () => {
    usePlaybackStore.getState().seek(0);
    render(<DecisionView />);
    expect(screen.queryAllByRole("listitem")).toHaveLength(0);
    for (const [index, decision] of decisionRecords.entries()) {
      act(() => usePlaybackStore.getState().seek(decision.time_s - 1));
      expect(screen.queryAllByRole("listitem")).toHaveLength(index);
      act(() => usePlaybackStore.getState().seek(decision.time_s));
      expect(screen.getAllByRole("listitem")).toHaveLength(index + 1);
    }
    act(() => usePlaybackStore.getState().seek(0));
    expect(screen.queryAllByRole("listitem")).toHaveLength(0);
  });

  it("uses McGill platform and station IDs and keeps every decision within the run", () => {
    for (const decision of decisionRecords) {
      const platform = stationViewData.platforms.find((item) => item.platform_id === decision.platform_id);
      expect(platform).toBeDefined();
      expect(decision.station_id).toBe(platform?.stop_id);
      expect(decision.time_s).toBeLessThanOrEqual(stationViewData.duration_s);
    }
  });

  it("hides McGill decisions when another connection is selected", () => {
    render(<DecisionView />);
    expect(screen.getAllByRole("listitem")).toHaveLength(3);
    act(() => usePlaybackStore.getState().selectConnection(connectionRuns[0].connections[0].id));
    act(() => usePlaybackStore.getState().seek(360));
    expect(screen.queryAllByRole("listitem")).toHaveLength(0);
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
