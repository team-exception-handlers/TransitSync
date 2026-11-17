// AI contribution: 50% or more AI-generated
// @vitest-environment jsdom
/** Verify Canvas consumes the same snapshots as the clock, including rewinds. */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, render, screen } from "@testing-library/react";
import { StationCanvas } from "../../src/components/station-canvas";
import { stationViewData } from "../../src/data/stationViewData";
import { usePlaybackStore } from "../../src/store/usePlaybackStore";
import { startPlaybackClock } from "../../src/lib/playback-clock";
import type { StationViewData } from "../../src/types/stationView";

describe("StationCanvas", () => {
  const arc = vi.fn();
  const clearRect = vi.fn();
  const strokeRect = vi.fn();
  const moveTo = vi.fn();
  const lineTo = vi.fn();
  const stroke = vi.fn();
  const fill = vi.fn();
  beforeEach(() => {
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue({
      clearRect, arc, beginPath: vi.fn(), moveTo, lineTo,
      stroke, fillRect: vi.fn(), fillText: vi.fn(), fill,
      strokeRect, closePath: vi.fn(),
      setTransform: vi.fn(), scale: vi.fn(), translate: vi.fn(),
    } as unknown as CanvasRenderingContext2D);
    usePlaybackStore.getState().loadData(stationViewData);
  });
  afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.clearAllMocks(); vi.unstubAllGlobals(); });

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

  it("renders queued passengers as an outlined square, not a filled circle", () => {
    render(<StationCanvas />);
    // p-002 is "queued" at t=138 in the shared fixture.
    act(() => usePlaybackStore.getState().seek(138));
    expect(strokeRect).toHaveBeenCalledWith(405 - 4, 310 - 4, 8, 8);
    // The queued marker must not also draw a plain filled circle at that spot.
    expect(arc).not.toHaveBeenCalledWith(405, 310, 4, 0, 2 * Math.PI);
  });

  it("renders boarding, waiting and missed passengers as distinct shapes", () => {
    const base = stationViewData;
    const connectionId = base.connections[0].id;
    const fixture: StationViewData = {
      ...base,
      passenger_tracks: [
        {
          passenger_id: "boarding-passenger",
          group_id: "distinct-states",
          connection_id: connectionId,
          samples: [{ time_s: 10, position: { x: 50, y: 60 }, phase: "boarding" }],
        },
        {
          passenger_id: "waiting-passenger",
          group_id: "distinct-states",
          connection_id: connectionId,
          samples: [{ time_s: 10, position: { x: 70, y: 80 }, phase: "waiting" }],
        },
        {
          passenger_id: "missed-passenger",
          group_id: "distinct-states",
          connection_id: connectionId,
          samples: [{ time_s: 10, position: { x: 90, y: 100 }, phase: "missed" }],
        },
      ],
    };

    render(<StationCanvas />);
    act(() => {
      usePlaybackStore.getState().loadData(fixture);
      usePlaybackStore.getState().seek(10);
    });

    // Boarding: a filled triangle via moveTo/lineTo, not an arc.
    expect(moveTo).toHaveBeenCalledWith(50, 60 - 5);
    expect(lineTo).toHaveBeenCalledWith(50 + 5, 60 + 4);
    expect(lineTo).toHaveBeenCalledWith(50 - 5, 60 + 4);
    expect(arc).not.toHaveBeenCalledWith(50, 60, 4, 0, 2 * Math.PI);

    // Waiting: a filled circle that is also stroked (outlined), unlike plain walking dots.
    expect(arc).toHaveBeenCalledWith(70, 80, 4, 0, 2 * Math.PI);
    expect(stroke).toHaveBeenCalled();

    // Missed: an outlined circle plus a cross through it.
    expect(arc).toHaveBeenCalledWith(90, 100, 4, 0, 2 * Math.PI);
    expect(moveTo).toHaveBeenCalledWith(90 - 3, 100 - 3);
    expect(lineTo).toHaveBeenCalledWith(90 + 3, 100 + 3);
  });
});

describe("StationCanvas scaling", () => {
  const arc = vi.fn();
  const clearRect = vi.fn();
  const scaleSpy = vi.fn();
  const translateSpy = vi.fn();
  const setTransformSpy = vi.fn();
  const fillTextSpy = vi.fn();

  beforeEach(() => {
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue({
      clearRect, arc, beginPath: vi.fn(), moveTo: vi.fn(), lineTo: vi.fn(),
      stroke: vi.fn(), fillRect: vi.fn(), fillText: fillTextSpy, fill: vi.fn(),
      strokeRect: vi.fn(), closePath: vi.fn(),
      setTransform: setTransformSpy, scale: scaleSpy, translate: translateSpy,
    } as unknown as CanvasRenderingContext2D);
    usePlaybackStore.getState().loadData(stationViewData);
  });
  afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.clearAllMocks(); vi.unstubAllGlobals(); });

  it("observes the canvas after data loads and disconnects when it disappears", () => {
    const observe = vi.fn();
    const disconnect = vi.fn();
    let observerCallback: ResizeObserverCallback | undefined;
    class FakeResizeObserver {
      constructor(callback: ResizeObserverCallback) {
        observerCallback = callback;
      }
      observe = observe;
      disconnect = disconnect;
      unobserve() {}
    }
    vi.stubGlobal("ResizeObserver", FakeResizeObserver);
    usePlaybackStore.setState({ data: null });

    const { container, unmount } = render(<StationCanvas />);
    expect(screen.queryByRole("img")).toBeNull();
    expect(observe).not.toHaveBeenCalled();

    act(() => usePlaybackStore.getState().loadData(stationViewData));
    expect(observe).toHaveBeenCalledExactlyOnceWith(
      container.querySelector(".station-canvas-wrap"),
    );
    act(() => observerCallback?.(
      [{ contentRect: { width: 400, height: 600 } } as ResizeObserverEntry],
      {} as ResizeObserver,
    ));
    expect(scaleSpy).toHaveBeenCalledWith(0.5, 0.5);
    expect(screen.getByRole("img").style.width).toBe("400px");

    act(() => usePlaybackStore.setState({ data: null }));
    expect(disconnect).toHaveBeenCalledTimes(1);
    act(() => usePlaybackStore.getState().loadData(stationViewData));
    expect(observe).toHaveBeenCalledTimes(2);
    unmount();
    expect(disconnect).toHaveBeenCalledTimes(2);
  });

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

  it("draws the passenger count label in screen space, not inside the fit transform", () => {
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
    act(() => usePlaybackStore.getState().seek(85));

    const labelCall = fillTextSpy.mock.calls.find(
      (call) => typeof call[0] === "string" && call[0].startsWith("Passengers:")
    );
    expect(labelCall).toBeDefined();
    expect(labelCall?.[1]).toBe(12);
    expect(labelCall?.[2]).toBe(20);

    // The label must be emitted after the transform is reset, so the last
    // setTransform call precedes it and no further translate/scale(0.5) runs.
    const labelIndex = fillTextSpy.mock.invocationCallOrder.at(-1) ?? 0;
    const lastReset = setTransformSpy.mock.invocationCallOrder.at(-1) ?? 0;
    expect(lastReset).toBeLessThan(labelIndex);
  });
});

describe("StationCanvas station layout (#65 item 1: platforms and connections)", () => {
  const arc = vi.fn();
  const fillRect = vi.fn();
  const moveTo = vi.fn();
  const lineTo = vi.fn();
  const stroke = vi.fn();

  beforeEach(() => {
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue({
      clearRect: vi.fn(), arc, beginPath: vi.fn(), moveTo, lineTo,
      stroke, fillRect, fillText: vi.fn(), fill: vi.fn(),
      strokeRect: vi.fn(), closePath: vi.fn(),
      setTransform: vi.fn(), scale: vi.fn(), translate: vi.fn(),
    } as unknown as CanvasRenderingContext2D);
    usePlaybackStore.getState().loadData(stationViewData);
  });
  afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.clearAllMocks(); });

  it("draws a platform rectangle at every recorded platform position", () => {
    render(<StationCanvas />);

    for (const platform of stationViewData.platforms) {
      expect(fillRect).toHaveBeenCalledWith(
        platform.position.x - 135,
        platform.position.y - 10,
        270,
        20,
      );
    }
  });

  it("traces every corridor polyline through all of its recorded points", () => {
    render(<StationCanvas />);

    for (const corridor of stationViewData.corridors) {
      const [first, ...rest] = corridor.path;
      expect(moveTo).toHaveBeenCalledWith(first.x, first.y);
      for (const point of rest) {
        expect(lineTo).toHaveBeenCalledWith(point.x, point.y);
      }
    }
    expect(stroke).toHaveBeenCalled();
  });

  it("renders a corridor for every connection in the data, keyed by corridor_id", () => {
    render(<StationCanvas />);

    for (const connection of stationViewData.connections) {
      const corridor = stationViewData.corridors.find(
        (item) => item.id === connection.corridor_id,
      );
      expect(corridor).toBeDefined();
      const [first] = corridor.path;
      expect(moveTo).toHaveBeenCalledWith(first.x, first.y);
    }
  });
});

describe("StationCanvas playback movement (#65 AC: selected connection + playing -> passengers move)", () => {
  const arc = vi.fn();
  let now = 0;
  let nextId = 0;
  let stop: () => void;
  const frames = new Map<number, FrameRequestCallback>();

  const frameAt = (timestamp: number) => {
    now = timestamp;
    const pending = [...frames.values()];
    frames.clear();
    pending.forEach((callback) => callback(now));
  };

  beforeEach(() => {
    now = 0;
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue({
      clearRect: vi.fn(), arc, beginPath: vi.fn(), moveTo: vi.fn(), lineTo: vi.fn(),
      stroke: vi.fn(), fillRect: vi.fn(), fillText: vi.fn(), fill: vi.fn(),
      strokeRect: vi.fn(), closePath: vi.fn(),
      setTransform: vi.fn(), scale: vi.fn(), translate: vi.fn(),
    } as unknown as CanvasRenderingContext2D);
    vi.spyOn(performance, "now").mockImplementation(() => now);
    vi.stubGlobal("requestAnimationFrame", (callback: FrameRequestCallback) => {
      frames.set(++nextId, callback);
      return nextId;
    });
    vi.stubGlobal("cancelAnimationFrame", (id: number) => frames.delete(id));
    usePlaybackStore.getState().loadData(stationViewData);
    stop = startPlaybackClock();
  });
  afterEach(() => {
    stop();
    frames.clear();
    cleanup();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("draws the passenger at a new interpolated position each frame while playing, with no seek or re-selection", () => {
    render(<StationCanvas />);
    expect(usePlaybackStore.getState().selectedConnectionId).toBe(
      stationViewData.connections[0].id,
    );

    act(() => usePlaybackStore.getState().play());
    expect(usePlaybackStore.getState().isPlaying).toBe(true);

    act(() => frameAt(85_000));
    expect(arc).toHaveBeenCalledWith(389, 135, 4, 0, 2 * Math.PI);
    expect(usePlaybackStore.getState().isPlaying).toBe(true);
    arc.mockClear();

    act(() => frameAt(95_000));
    expect(arc).toHaveBeenCalledWith(405, 135, 4, 0, 2 * Math.PI);
    expect(arc).not.toHaveBeenCalledWith(389, 135, 4, 0, 2 * Math.PI);
    expect(usePlaybackStore.getState().isPlaying).toBe(true);
    expect(usePlaybackStore.getState().currentTime_s).toBe(95);
  });
});
