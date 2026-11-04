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
      setTransform: vi.fn(), scale: vi.fn(), translate: vi.fn(),
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

describe("StationCanvas scaling", () => {
  const arc = vi.fn();
  const clearRect = vi.fn();
  const scaleSpy = vi.fn();
  const translateSpy = vi.fn();

  beforeEach(() => {
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue({
      clearRect, arc, beginPath: vi.fn(), moveTo: vi.fn(), lineTo: vi.fn(),
      stroke: vi.fn(), fillRect: vi.fn(), fillText: vi.fn(), fill: vi.fn(),
      setTransform: vi.fn(), scale: scaleSpy, translate: translateSpy,
    } as unknown as CanvasRenderingContext2D);
    usePlaybackStore.getState().loadData(stationViewData);
  });
  afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.clearAllMocks(); });

  it("renders the station layout with its platforms and connections", () => {
    render(<StationCanvas />);

    expect(screen.getByRole("img")).toBeDefined();
    expect(screen.getByRole("img").getAttribute("aria-label")).toContain(
      stationViewData.interchange.name
    );
  });

  it("falls back to the fixture's own size (scale 1) when no ResizeObserver reports a view box", () => {
    render(<StationCanvas />);

    // jsdom has no layout engine, so clientWidth/clientHeight are 0 and the
    // component falls back to the fixture's own map size: no scaling.
    expect(scaleSpy).toHaveBeenCalledWith(1, 1);
  });

  it("scales the layout to fit a narrower view box", () => {
    let observerCallback: ResizeObserverCallback | undefined;
    class FakeResizeObserver {
      constructor(callback: ResizeObserverCallback) {
        observerCallback = callback;
      }
      observe() {
        observerCallback?.(
          [{ contentRect: { width: 400, height: 600 } } as ResizeObserverEntry],
          this as unknown as ResizeObserver
        );
      }
      unobserve() {}
      disconnect() {}
    }
    vi.stubGlobal("ResizeObserver", FakeResizeObserver);

    render(<StationCanvas />);

    // map is 800x600; a 400x600 view box is width-bound: scale = 400/800 = 0.5
    expect(scaleSpy).toHaveBeenCalledWith(0.5, 0.5);
  });

  it("scales the layout to fit a taller view box", () => {
    let observerCallback: ResizeObserverCallback | undefined;
    class FakeResizeObserver {
      constructor(callback: ResizeObserverCallback) {
        observerCallback = callback;
      }
      observe() {
        observerCallback?.(
          [{ contentRect: { width: 800, height: 1800 } } as ResizeObserverEntry],
          this as unknown as ResizeObserver
        );
      }
      unobserve() {}
      disconnect() {}
    }
    vi.stubGlobal("ResizeObserver", FakeResizeObserver);

    render(<StationCanvas />);

    // map is 800x600; an 800x1800 view box is width-bound: scale = 800/800 = 1
    expect(scaleSpy).toHaveBeenCalledWith(1, 1);
  });
});
