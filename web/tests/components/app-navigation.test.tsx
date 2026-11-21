// AI contribution: 50% or more AI-generated
// @vitest-environment jsdom
/**
 * Sidebar navigation (#408): each item shows its screen, the current item is
 * marked for screen readers, and leaving the station view keeps playback.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import App from "../../src/App";
import { usePlaybackStore } from "../../src/store/usePlaybackStore";
import { useViewStore } from "../../src/store/useViewStore";
import type { TimeSeriesData } from "../../src/types/stationView";

// Looked up inside the sidebar so a same-named button elsewhere cannot match.
const navItem = (label: string) =>
  within(screen.getByRole("navigation", { name: "Workspace" })).getByRole("button", { name: label });
const openView = (label: string) => fireEvent.click(navItem(label));

// Two 5-minute buckets, enough for the delay chart to draw.
const TIME_SERIES: TimeSeriesData = {
  start_s: 0,
  end_s: 600,
  bucket_s: 300,
  buckets: [
    { start_s: 0, end_s: 300, average_passenger_delay_s: 12.5, passenger_count: 4 },
    { start_s: 300, end_s: 600, average_passenger_delay_s: 20, passenger_count: 6 },
  ],
  hold_events: [],
};

beforeEach(() => {
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(null);
  // Recharts sizes its chart with ResizeObserver, which jsdom does not provide.
  vi.stubGlobal("ResizeObserver", class {
    observe() { /* jsdom has no layout to observe */ }
    unobserve() { /* nothing observed */ }
    disconnect() { /* nothing observed */ }
  });
  useViewStore.setState({ activeView: "station" });
  usePlaybackStore.setState({ data: null, currentTime_s: 0, selectedConnectionId: null,
    availableRuns: [], availableConnections: null, isPlaying: false, updatedAt_ms: null });
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("sidebar navigation", () => {
  it("opens on the station view with that item marked current", () => {
    render(<App runLoader={null} />);

    expect(screen.getByRole("region", { name: "Station view" })).toBeDefined();
    expect(navItem("Station view").getAttribute("aria-current")).toBe("page");
    expect(navItem("Compare").getAttribute("aria-current")).toBeNull();
  });

  it("shows the delay chart on Results for a run with a time series", () => {
    render(<App runLoader={null} />);
    act(() => {
      const data = usePlaybackStore.getState().data;
      if (data === null) throw new Error("App did not load the fixture run");
      usePlaybackStore.setState({ data: { ...data, time_series: TIME_SERIES } });
    });
    openView("Results");

    expect(screen.getByRole("heading", { name: "Passenger delay over time" })).toBeDefined();
    expect(screen.queryByRole("region", { name: "Station view" })).toBeNull();
  });

  it("explains an empty Results screen when the run has no time series", () => {
    render(<App runLoader={null} />);
    openView("Results");

    expect(screen.getByText(/Results appear here once a simulation run is loaded/)).toBeDefined();
    expect(screen.queryByRole("heading", { name: "Passenger delay over time" })).toBeNull();
  });

  it("shows the run settings on Scenario setup", () => {
    render(<App runLoader={null} scenarioRunner={null} />);
    openView("Scenario setup");

    expect(screen.getByRole("heading", { name: "Run settings" })).toBeDefined();
    expect(navItem("Scenario setup").getAttribute("aria-current")).toBe("page");
    expect(navItem("Station view").getAttribute("aria-current")).toBeNull();
  });

  it("shows a placeholder naming the story that fills Sources", () => {
    render(<App runLoader={null} />);
    openView("Sources");

    expect(screen.getByRole("heading", { name: "Sources" })).toBeDefined();
    expect(screen.getByText("This screen is filled by US-7.2.")).toBeDefined();
  });

  it("shows the side-by-side comparison screen on Compare", () => {
    render(<App runLoader={null} comparisonRunner={null} />);
    openView("Compare");

    expect(screen.getByRole("heading", { name: "Compare" })).toBeDefined();
    expect(screen.getByText(/Comparing runs needs the simulation API/)).toBeDefined();
    expect(navItem("Compare").getAttribute("aria-current")).toBe("page");
  });

  it("keeps the playback position and connection after leaving the station view", () => {
    render(<App runLoader={null} />);
    fireEvent.change(screen.getByRole("slider", { name: "Seek simulation time" }), { target: { value: "85" } });
    const connection = usePlaybackStore.getState().selectedConnectionId;

    openView("Results");
    openView("Compare");
    openView("Station view");

    expect(usePlaybackStore.getState().currentTime_s).toBe(85);
    expect(usePlaybackStore.getState().selectedConnectionId).toBe(connection);
    // The remounted canvas draws the same moment, not a restarted run.
    expect(screen.getByLabelText(/simulation seconds/).getAttribute("aria-label")).toContain("85.0");
  });
});
