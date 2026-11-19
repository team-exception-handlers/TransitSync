// AI contribution: 50% or more AI-generated
// @vitest-environment jsdom
/** Clicking passengers on the station canvas selects, switches and clears the followed passenger (#237). */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { StationCanvas } from "../../src/components/station-canvas";
import { stationViewData } from "../../src/data/stationViewData";
import { samplePassengers } from "../../src/lib/samplePassengers";
import { usePlaybackStore } from "../../src/store/usePlaybackStore";
import type { PassengerTrack, StationViewData } from "../../src/types/stationView";

const RING = (x: number, y: number) => [x, y, 8, 0, 2 * Math.PI];

/** One track per position, all on the fixture's connection, each seen only at t = 10 s. */
function tracksAt(points: readonly { id: string; x: number; y: number }[]): PassengerTrack[] {
  return points.map(({ id, x, y }) => ({
    passenger_id: id,
    group_id: "selection-test",
    connection_id: stationViewData.connections[0].id,
    samples: [{ time_s: 10, position: { x, y }, phase: "walking" }],
  }));
}

function loadAtTen(tracks: PassengerTrack[]) {
  const fixture: StationViewData = { ...stationViewData, passenger_tracks: tracks };
  act(() => {
    usePlaybackStore.getState().loadData(fixture);
    usePlaybackStore.getState().seek(10);
  });
}

describe("StationCanvas passenger selection (#237)", () => {
  const arc = vi.fn();
  const fillText = vi.fn();

  beforeEach(() => {
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue({
      clearRect: vi.fn(), arc, beginPath: vi.fn(), moveTo: vi.fn(), lineTo: vi.fn(),
      stroke: vi.fn(), fillRect: vi.fn(), fillText, fill: vi.fn(),
      strokeRect: vi.fn(), closePath: vi.fn(),
      setTransform: vi.fn(), scale: vi.fn(), translate: vi.fn(),
    } as unknown as CanvasRenderingContext2D);
    usePlaybackStore.getState().loadData(stationViewData);
  });
  afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.clearAllMocks(); });

  it("follows the clicked passenger, rings them and names them in the label", () => {
    render(<StationCanvas />);
    // p-001 is walking at (389, 135) at t = 85 in the shared fixture; jsdom draws unscaled.
    act(() => usePlaybackStore.getState().seek(85));

    fireEvent.click(screen.getByRole("img"), { clientX: 391, clientY: 137 });

    expect(usePlaybackStore.getState().selectedPassengerId).toBe("p-001");
    expect(arc).toHaveBeenCalledWith(...RING(389, 135));
    expect(screen.getByRole("img").getAttribute("aria-label")).toContain("following passenger p-001");
  });

  it("switches to another passenger, then clears the pick on an empty click", () => {
    render(<StationCanvas />);
    loadAtTen(tracksAt([{ id: "left", x: 50, y: 60 }, { id: "right", x: 200, y: 60 }]));
    const canvas = screen.getByRole("img");

    fireEvent.click(canvas, { clientX: 50, clientY: 60 });
    fireEvent.click(canvas, { clientX: 200, clientY: 60 });
    expect(usePlaybackStore.getState().selectedPassengerId).toBe("right");

    arc.mockClear();
    fireEvent.click(canvas, { clientX: 120, clientY: 300 });
    expect(usePlaybackStore.getState().selectedPassengerId).toBeNull();
    expect(arc).not.toHaveBeenCalledWith(...RING(200, 60));
    expect(canvas.getAttribute("aria-label")).not.toContain("following");
  });

  it("still draws the followed passenger when the 60-marker sample leaves them out", () => {
    const points = Array.from({ length: 100 }, (_, index) => ({
      id: `p-${String(index).padStart(3, "0")}`, x: 100 + index * 5, y: 200,
    }));
    render(<StationCanvas />);
    loadAtTen(tracksAt(points));
    const plain = samplePassengers(usePlaybackStore.getState().snapshot()?.passengers ?? [], 60);
    const outside = points.find((point) => !plain.sampled.some((item) => item.passenger_id === point.id));
    expect(outside).toBeDefined();
    const followed = outside ?? points[0];

    act(() => usePlaybackStore.getState().selectPassenger(followed.id));

    expect(arc).toHaveBeenCalledWith(followed.x, followed.y, 4, 0, 2 * Math.PI);
    expect(arc).toHaveBeenCalledWith(...RING(followed.x, followed.y));
    expect(fillText).toHaveBeenLastCalledWith("Passengers: 100 (showing 61)", 12, 20);
  });

  it("does not change the simulated positions when a passenger is followed", () => {
    act(() => usePlaybackStore.getState().seek(85));
    const before = usePlaybackStore.getState().snapshot();

    act(() => usePlaybackStore.getState().selectPassenger("p-001"));

    expect(usePlaybackStore.getState().snapshot()).toEqual(before);
  });
});
