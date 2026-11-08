// AI contribution: 50% or more AI-generated
// @vitest-environment jsdom
/**
 * High-demand integration cover for the marker budget: the shared mock run
 * only carries three passengers, so the sampling branch and its
 * "(showing M)" label never run against fixture data. This drives the real
 * component with a crowd and asserts both the cap and the true-count label.
 *
 * Each assertion clears the canvas spies first, so it reads exactly one
 * redraw rather than everything drawn since mount.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, render } from "@testing-library/react";
import { StationCanvas } from "../../src/components/station-canvas";
import { stationViewData } from "../../src/data/stationViewData";
import { usePlaybackStore } from "../../src/store/usePlaybackStore";
import type { StationViewData } from "../../src/types/stationView";

const CROWD = 150;
const BUDGET = 60;

/** A run identical to the shared fixture except for a crowd of walking passengers. */
function highDemandRun(): StationViewData {
  const connectionId = stationViewData.connections[0].id;
  return {
    ...stationViewData,
    passenger_tracks: Array.from({ length: CROWD }, (_, index) => ({
      passenger_id: `crowd-${index}`,
      group_id: "crowd",
      connection_id: connectionId,
      samples: [
        {
          time_s: 10,
          position: { x: 100 + (index % 50), y: 200 + (index % 30) },
          phase: "walking" as const,
        },
      ],
    })),
  };
}

describe("StationCanvas under high demand", () => {
  const arc = vi.fn();
  const fillText = vi.fn();

  /** Markers are the radius-4 arcs; platforms and trains draw with fillRect. */
  const markerPositions = () =>
    arc.mock.calls.filter((call) => call[2] === 4).map((call) => `${call[0]},${call[1]}`);

  beforeEach(() => {
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue({
      clearRect: vi.fn(), arc, beginPath: vi.fn(), moveTo: vi.fn(), lineTo: vi.fn(),
      stroke: vi.fn(), fillRect: vi.fn(), fillText, fill: vi.fn(),
      strokeRect: vi.fn(), closePath: vi.fn(),
      setTransform: vi.fn(), scale: vi.fn(), translate: vi.fn(),
    } as unknown as CanvasRenderingContext2D);
    usePlaybackStore.getState().loadData(highDemandRun());
  });
  afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.clearAllMocks(); });

  it("draws at most the marker budget and labels the true count", () => {
    render(<StationCanvas />);
    arc.mockClear();
    fillText.mockClear();
    act(() => usePlaybackStore.getState().seek(10));

    expect(markerPositions()).toHaveLength(BUDGET);

    const label = fillText.mock.calls
      .map((call) => call[0])
      .find((text) => typeof text === "string" && text.startsWith("Passengers:"));
    expect(label).toBe(`Passengers: ${CROWD} (showing ${BUDGET})`);
  });

  it("keeps the drawn sample stable across a seek away and back", () => {
    render(<StationCanvas />);
    arc.mockClear();
    act(() => usePlaybackStore.getState().seek(10));
    const first = markerPositions();

    act(() => usePlaybackStore.getState().seek(40));
    arc.mockClear();
    act(() => usePlaybackStore.getState().seek(10));

    expect(markerPositions()).toEqual(first);
  });
});
