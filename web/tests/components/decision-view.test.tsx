// AI contribution: 50% or more AI-generated
// @vitest-environment jsdom
/** Refused and clamped decisions are marked distinctly from applied ones, and
 * each decision shows what the strategy saw next to the true value. */
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { act, cleanup, render, screen, within } from "@testing-library/react";
import { DecisionView } from "../../src/components/decision-view";
import { decisionRecords, estimateRecords } from "../../src/data/decisions";
import { decisionStatus, estimatesFor } from "../../src/types/decision";
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

  it("shows what the strategy saw next to the true value, with the gap", () => {
    render(<DecisionView />);
    const row = screen.getByText("T-101").closest("li") as HTMLElement;
    const cellsOf = (label: string) =>
      within(within(row).getByText(label).closest("tr") as HTMLElement)
        .getAllByRole("cell")
        .map((cell) => cell.textContent);

    // Seen 181 s against a true 165 s: the strategy thinks REM-12 is 16 s later
    expect(cellsOf("REM-12 arrival")).toEqual(["REM-12 arrival", "181 s", "165 s", "+16 s"]);
    expect(cellsOf("G-12 still walking")).toEqual(["G-12 still walking", "38", "42", "-4"]);
  });

  it("skips a value with nothing to predict but keeps the train's other values", () => {
    render(<DecisionView />);
    const row = screen.getByText("T-317").closest("li") as HTMLElement;

    // REM-09 has no next stop, so only its load is compared
    expect(within(row).queryByText("REM-09 arrival")).toBeNull();
    expect(within(row).getByText("REM-09 load")).toBeDefined();
  });

  it("matches estimates to a decision by time, train and platform only", () => {
    for (const record of estimateRecords) {
      const decision = decisionRecords.find((item) => item.time_s === record.time_s);
      expect(decision && estimatesFor(decision, estimateRecords)).toBe(record);
    }
    // One second off is a different decision, so no comparison is shown
    const shifted = { ...decisionRecords[0], time_s: decisionRecords[0].time_s + 1 };
    expect(estimatesFor(shifted, estimateRecords)).toBeUndefined();
  });

  it("shows the requested duration alongside the applied one for a refused decision", () => {
    render(<DecisionView />);

    const refused = decisionRecords.find((d) => decisionStatus(d) === "refused");
    expect(refused).toBeDefined();
    const row = screen.getByText(refused!.train_id).closest("li");

    expect(row?.textContent).toContain(`requested ${refused!.requested_s}s`);
    expect(row?.textContent).toContain(`applied ${refused!.applied_s}s`);
  });

  /** Load the McGill view as a simulated run carrying these decisions. */
  const loadSimulated = (decisions: unknown[]) => {
    usePlaybackStore.getState().loadData({ ...stationViewData, decisions });
    usePlaybackStore.getState().seek(stationViewData.duration_s);
  };

  it("shows no decisions for a simulated run that never held a train", () => {
    // No control returns an empty list; the fixture must not fill the gap
    loadSimulated([]);
    render(<DecisionView />);

    expect(screen.queryAllByRole("listitem")).toHaveLength(0);
  });

  it("shows a simulated run's own holds, rounded, without fixture estimates", () => {
    loadSimulated([
      {
        time_s: 60,
        train_id: "stm:T9",
        station_id: "32",
        platform_id: "green_mcgill_0",
        requested_s: 269.9999999999999,
        applied_s: 269.9999999999999,
        reason: "headway_regulation",
      },
    ]);
    render(<DecisionView />);

    const [row] = screen.getAllByRole("listitem");
    expect(row.textContent).toContain("stm:T9");
    expect(row.textContent).toContain("270s");
    expect(row.textContent).not.toContain("269.99");
    expect(within(row).queryByRole("table")).toBeNull();
    expect(screen.queryByText("T-101")).toBeNull();
  });
});
