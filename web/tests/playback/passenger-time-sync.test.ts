// AI contribution: 50% or more AI-generated
/**
 * Passenger positions follow simulation time (#72): as the playback clock
 * advances, after a speed change, and after seeking or rewinding.
 *
 * The run is hand-built on a straight 100-unit corridor so every expected
 * position can be worked out by hand: a passenger walking from t=10 s to
 * t=50 s covers 2.5 units per second.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { startPlaybackClock } from "../../src/lib/playback-clock";
import { parseStationViewData } from "../../src/lib/validateStationView";
import { usePlaybackStore } from "../../src/store/usePlaybackStore";

const START = { x: 0, y: 0 };
const END = { x: 100, y: 0 };

/** One platform record; only the ID, stop and position differ between the two. */
function platform(id: string, position: { x: number; y: number }) {
  return {
    platform_id: id, interchange_id: "sync", line_id: "rem", direction_id: 0,
    direction_label: id, stop_id: `stop-${id}`, stop_name: id, route_ids: [],
    station_id: `station-${id}`, source_feed_id: "fixture", position, color: "#000000",
  };
}

/**
 * Two passengers on one connection, in a 120 s run:
 * - "early" walks 10-50 s, queues, waits from 60 s, boards at 80 s, is gone at 90 s
 * - "late" walks 100-110 s and is still waiting when the run ends
 */
function buildRun() {
  return parseStationViewData({
    schema_version: 1,
    interchange: { id: "sync", name: "Time sync fixture" },
    start_clock_s: 0,
    duration_s: 120,
    map: { width: 100, height: 20 },
    stations: [
      { id: "station-a", name: "A", line_id: "rem", position: START },
      { id: "station-b", name: "B", line_id: "green", position: END },
    ],
    platforms: [platform("a", START), platform("b", END)],
    corridors: [{ id: "corridor", label: "Corridor", from_platform_id: "a",
      to_platform_id: "b", path: [START, END] }],
    connections: [{ id: "a-b", label: "A to B", from_platform_id: "a",
      to_platform_id: "b", corridor_id: "corridor" }],
    passenger_tracks: [
      { passenger_id: "early", group_id: "g1", connection_id: "a-b", samples: [
        { time_s: 10, position: START, phase: "walking" },
        { time_s: 50, position: END, phase: "queued" },
        { time_s: 60, position: END, phase: "waiting" },
        { time_s: 80, position: END, phase: "boarding" },
        { time_s: 90, position: END, phase: "boarded" },
      ] },
      { passenger_id: "late", group_id: "g2", connection_id: "a-b", samples: [
        { time_s: 100, position: START, phase: "walking" },
        { time_s: 110, position: END, phase: "waiting" },
      ] },
    ],
    train_events: [],
  });
}

describe("passenger positions follow simulation time (#72)", () => {
  let now = 0;
  let nextId = 0;
  let stop: () => void;
  const frames = new Map<number, FrameRequestCallback>();
  const state = () => usePlaybackStore.getState();
  /** Passengers in the current snapshot as "id phase x" strings. */
  const shown = () => (state().snapshot()?.passengers ?? [])
    .map((passenger) => `${passenger.passenger_id} ${passenger.phase} ${passenger.position.x}`);
  /** Move the fake wall clock to `timestamp` ms and run the pending frame. */
  const frameAt = (timestamp: number) => {
    now = timestamp;
    const pending = [...frames.values()];
    frames.clear();
    pending.forEach((callback) => callback(now));
  };

  beforeEach(() => {
    now = 0;
    vi.spyOn(performance, "now").mockImplementation(() => now);
    vi.stubGlobal("requestAnimationFrame", (callback: FrameRequestCallback) => {
      frames.set(++nextId, callback);
      return nextId;
    });
    vi.stubGlobal("cancelAnimationFrame", (id: number) => frames.delete(id));
    state().loadData(buildRun());
    stop = startPlaybackClock();
  });

  afterEach(() => {
    stop();
    frames.clear();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it.each([
    [0, []],
    [9.9, []],
    [10, ["early walking 0"]],
    [20, ["early walking 25"]],
    [30, ["early walking 50"]],
    [50, ["early queued 100"]],
    [70, ["early waiting 100"]],
    [85, ["early boarding 100"]],
    [95, []],
    [105, ["late walking 50"]],
  ])("shows the hand-calculated positions at %d s", (time_s, expected) => {
    state().seek(time_s);

    expect(shown()).toStrictEqual(expected);
  });

  it("moves passengers as the playback clock advances", () => {
    state().play();
    frameAt(10_000);
    expect(shown()).toStrictEqual(["early walking 0"]);

    frameAt(20_000);
    expect(state().currentTime_s).toBe(20);
    expect(shown()).toStrictEqual(["early walking 25"]);
  });

  it("keeps positions tied to simulation time, not wall time, after a speed change", () => {
    state().play();
    frameAt(20_000);
    state().setSpeed(2);
    // Five wall seconds at 2x are ten simulated seconds: 20 s becomes 30 s.
    frameAt(25_000);

    expect(state().currentTime_s).toBe(30);
    expect(shown()).toStrictEqual(["early walking 50"]);
  });

  it("shows nobody before the first passenger enters, even for a negative seek", () => {
    state().seek(-5);

    expect(state().currentTime_s).toBe(0);
    expect(shown()).toStrictEqual([]);
  });

  it("holds the final state at and beyond the end of the run", () => {
    state().seek(120);
    const atEnd = shown();
    state().seek(999);

    expect(state().currentTime_s).toBe(120);
    expect(atEnd).toStrictEqual(["late waiting 100"]);
    expect(shown()).toStrictEqual(atEnd);
  });

  it("stops at the end of the run when playback reaches it", () => {
    state().seek(115);
    state().play();
    frameAt(60_000);

    expect(state().isPlaying).toBe(false);
    expect(shown()).toStrictEqual(["late waiting 100"]);
  });

  it("rebuilds earlier positions after seeking backwards", () => {
    state().seek(30);
    const before = state().snapshot();
    state().seek(95);
    expect(shown()).toStrictEqual([]);

    state().seek(30);

    expect(state().snapshot()).toStrictEqual(before);
    expect(shown()).toStrictEqual(["early walking 50"]);
  });

  it("brings a boarded passenger back when rewinding 30 s during playback", () => {
    state().seek(95);
    state().play();
    frameAt(5_000);
    expect(shown()).toStrictEqual(["late walking 0"]);

    state().rewind30();

    // 100 s - 30 s = 70 s: "early" is waiting again and "late" has not arrived.
    expect(state().currentTime_s).toBe(70);
    expect(shown()).toStrictEqual(["early waiting 100"]);
    expect(state().isPlaying).toBe(true);
  });
});
