// AI contribution: 50% or more AI-generated
// @vitest-environment jsdom
/**
 * Compare screen (US-4.1, #230): two labelled runs side by side that one
 * shared playback clock drives, with the holding badge only on the side
 * that holds.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import App from "../../src/App";
import { stationViewData } from "../../src/data/stationViewData";
import { DEFAULT_RUN_SETTINGS } from "../../src/lib/run-settings";
import type { ComparisonRunner, SimulationComparison } from "../../src/lib/simulation-api";
import { EMPTY_COMPARISON, useComparisonStore } from "../../src/store/useComparisonStore";
import { usePlaybackStore } from "../../src/store/usePlaybackStore";
import { useRunSettingsStore } from "../../src/store/useRunSettingsStore";
import { useViewStore } from "../../src/store/useViewStore";
import type { StationViewData, TimeSeriesData } from "../../src/types/stationView";

const HOLDING_TITLE = "With holding · Connection protection";

/** A time series with one 30 s hold starting at `holdAt`, or none. */
function timeSeries(holdAt: number | null): TimeSeriesData {
  return {
    start_s: 0, end_s: 360, bucket_s: 180, buckets: [],
    hold_events: holdAt === null ? [] : [{
      time_s: holdAt, train_id: "metro-1", station_id: "metro_mcgill",
      platform_id: "metro_mcgill_p1", applied_s: 30,
    }],
  };
}

const HOLDING_RUN: StationViewData = { ...stationViewData, time_series: timeSeries(100) };
const NO_HOLDING_RUN: StationViewData = { ...stationViewData, time_series: timeSeries(null) };
const PAIR: SimulationComparison = {
  holding: HOLDING_RUN,
  noHolding: NO_HOLDING_RUN,
  holdingStrategy: "connection_protection",
  startingConditions: { serviceDate: "2026-10-05", masterSeed: 42, duration_s: 360 },
  passengerSplit: {
    better_off: 45, worse_off: 2, unaffected: 1238, not_compared: 82,
    total_time_saved_s: 11490, total_time_lost_s: 100,
    average_time_saved_s: 255.33, average_time_lost_s: 50,
  },
};

const panel = (name: string) => screen.getByRole("region", { name });
/** The simulation time each panel's canvas announces, e.g. "120.0". */
function panelTimes(): string[] {
  return [panel("No holding"), panel(HOLDING_TITLE)].map((region) => {
    const label = within(region).getByLabelText(/simulation seconds/).getAttribute("aria-label") ?? "";
    return /at ([\d.]+) simulation seconds/.exec(label)?.[1] ?? "";
  });
}

/** Render the app on the Compare screen and wait for the pair to appear. */
async function openCompare(runner: ComparisonRunner | null = vi.fn<ComparisonRunner>(async () => PAIR)) {
  render(<App runLoader={null} comparisonRunner={runner} />);
  fireEvent.click(within(screen.getByRole("navigation", { name: "Workspace" }))
    .getByRole("button", { name: "Compare" }));
  if (runner !== null) await screen.findByRole("region", { name: "No holding" });
  return runner;
}

beforeEach(() => {
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(null);
  useViewStore.setState({ activeView: "station" });
  useComparisonStore.setState(EMPTY_COMPARISON);
  useRunSettingsStore.setState({ draft: DEFAULT_RUN_SETTINGS, applied: {} });
  usePlaybackStore.setState({ data: null, currentTime_s: 0, selectedConnectionId: null,
    availableRuns: [], availableConnections: null, isPlaying: false, updatedAt_ms: null });
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("CompareView", () => {
  it("shows both labelled runs and their shared starting conditions", async () => {
    const runner = await openCompare();

    expect(runner).toHaveBeenCalledTimes(1);
    expect(within(panel("No holding")).getByLabelText(/^No holding: /)).toBeDefined();
    expect(within(panel(HOLDING_TITLE)).getByLabelText(/^With holding/)).toBeDefined();
    expect(screen.getByText("Same starting conditions: 2026-10-05 · seed 42")).toBeDefined();
    expect(screen.getByText("Both runs loaded · one shared playback clock")).toBeDefined();
  });

  it("shows each side's time saved and lost, mirrored, under its panel", async () => {
    await openCompare();
    const value = (name: string, label: string) =>
      within(panel(name)).getByText(label).nextSibling?.textContent;

    // Holding saved 45 passengers 11 490 s (3 h 11 min) and cost 2 of them 100 s
    expect(value(HOLDING_TITLE, "Time saved (whole run)")).toBe("3 h 11 min · 45 passengers");
    expect(value(HOLDING_TITLE, "Time lost (whole run)")).toBe("1 min 40 s · 2 passengers");
    expect(value("No holding", "Time saved (whole run)")).toBe("1 min 40 s · 2 passengers");
    expect(value("No holding", "Time lost (whole run)")).toBe("3 h 11 min · 45 passengers");
    expect(screen.getByText(/Changes of\s+30 s or less count as unaffected/)).toBeDefined();
  });

  it("runs the API defaults, not unrun slider values, before anything is run", async () => {
    // The user moved a slider but never clicked "Run scenario".
    useRunSettingsStore.getState().update({ passenger_flow: "High" });

    const runner = await openCompare();

    expect(runner).toHaveBeenCalledWith(expect.any(String), DEFAULT_RUN_SETTINGS, expect.anything());
  });

  it("keeps both panels on the same time through seek, play and pause", async () => {
    await openCompare();
    act(() => usePlaybackStore.getState().seek(120));
    expect(panelTimes()).toEqual(["120.0", "120.0"]);

    // Ten wall-clock seconds of playback at 1x move both panels by ten seconds.
    const now = vi.spyOn(performance, "now").mockReturnValue(1_000);
    act(() => usePlaybackStore.getState().play());
    now.mockReturnValue(11_000);
    act(() => usePlaybackStore.getState().advance());
    act(() => usePlaybackStore.getState().pause());

    expect(panelTimes()).toEqual(["130.0", "130.0"]);
  });

  it("rewinds both panels with the shared rewind button", async () => {
    await openCompare();
    act(() => usePlaybackStore.getState().seek(120));

    fireEvent.click(screen.getByRole("button", { name: "Rewind 30 seconds" }));

    expect(panelTimes()).toEqual(["90.0", "90.0"]);
  });

  it("shows the holding badge only on the holding side, only during the hold", async () => {
    await openCompare();

    act(() => usePlaybackStore.getState().seek(110));
    expect(within(panel(HOLDING_TITLE)).getByText("Holding")).toBeDefined();
    expect(within(panel("No holding")).queryByText("Holding")).toBeNull();
    expect(within(panel(HOLDING_TITLE)).getByText("Holds so far").nextSibling?.textContent).toBe("1");

    // The hold lasts 30 s from t = 100, so it is over at t = 130.
    act(() => usePlaybackStore.getState().seek(130));
    expect(within(panel(HOLDING_TITLE)).queryByText("Holding")).toBeNull();
  });

  it("starts both runs at time 0 when a new pair loads", async () => {
    render(<App runLoader={null} comparisonRunner={null} />);
    act(() => usePlaybackStore.getState().seek(200));
    cleanup();

    await openCompare();

    expect(usePlaybackStore.getState().currentTime_s).toBe(0);
  });

  it("explains that comparing needs the API when there is no runner", async () => {
    await openCompare(null);

    expect(screen.getByText(/Comparing runs needs the simulation API/)).toBeDefined();
    expect(screen.queryByRole("region", { name: "No holding" })).toBeNull();
  });

  it("hides the previous connection's runs when loading a new connection fails", async () => {
    const runner = vi.fn<ComparisonRunner>(async () => PAIR);
    await openCompare(runner);
    const { availableRuns, selectedConnectionId } = usePlaybackStore.getState();
    const other = availableRuns.flatMap((run) => run.connections)
      .find((connection) => connection.id !== selectedConnectionId);
    if (other === undefined) throw new Error("The mock runs need a second connection");

    runner.mockRejectedValueOnce(new Error("The simulation run failed on the server (HTTP 500)."));
    act(() => usePlaybackStore.getState().selectConnection(other.id));

    expect((await screen.findByRole("alert")).textContent).toContain("HTTP 500");
    expect(screen.getByRole("heading", { level: 1 }).textContent).toContain(other.label);
    // The stored pair is for the first connection, so neither panel nor its
    // starting conditions may sit under the new heading.
    expect(screen.queryByRole("region", { name: "No holding" })).toBeNull();
    expect(screen.queryByRole("region", { name: HOLDING_TITLE })).toBeNull();
    expect(screen.queryByText(/Same starting conditions/)).toBeNull();
  });

  it("reports a failed load as an alert", async () => {
    const failing = vi.fn<ComparisonRunner>(async () => {
      throw new Error("The simulation run failed on the server (HTTP 500).");
    });
    render(<App runLoader={null} comparisonRunner={failing} />);
    act(() => useViewStore.getState().setView("compare"));

    expect((await screen.findByRole("alert")).textContent).toContain("HTTP 500");
    expect(screen.getByText("Comparison failed")).toBeDefined();
  });
});
