// AI contribution: 50% or more AI-generated
// @vitest-environment jsdom
/** Verify Canvas consumes the same snapshots as the clock, including rewinds. */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, render, screen } from "@testing-library/react";
import { StationCanvas } from "../../src/components/station-canvas";
import { stationViewData } from "../../src/data/stationViewData";
import { usePlaybackStore } from "../../src/store/usePlaybackStore";

describe("StationCanvas", () => {
  const arc = vi.fn();
  const clearRect = vi.fn();
  beforeEach(() => {
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue({
      clearRect, arc, beginPath: vi.fn(), moveTo: vi.fn(), lineTo: vi.fn(),
      stroke: vi.fn(), fillRect: vi.fn(), fillText: vi.fn(), fill: vi.fn(),
    } as unknown as CanvasRenderingContext2D);
    usePlaybackStore.getState().loadData(stationViewData);
  });
  afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.clearAllMocks(); });

  it("redraws the recorded passenger position after forward and backward seeks", () => {
    render(<StationCanvas />);
    expect(arc).not.toHaveBeenCalled();
    act(() => usePlaybackStore.getState().seek(85));
    expect(arc).toHaveBeenCalledWith(389, 135, 4, 0, 2 * Math.PI);
    act(() => usePlaybackStore.getState().seek(300));
    arc.mockClear();
    act(() => usePlaybackStore.getState().seek(85));
    expect(arc).toHaveBeenCalledWith(389, 135, 4, 0, 2 * Math.PI);
    expect(clearRect).toHaveBeenCalledTimes(4);
    expect(screen.getByRole("img").getAttribute("aria-label")).toContain("85.0");
  });
});
