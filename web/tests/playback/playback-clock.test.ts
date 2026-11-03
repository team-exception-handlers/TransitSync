// AI contribution: 50% or more AI-generated
/** Fake frames and a monotonic clock make playback tests independent of wall time. */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { stationViewData } from "../../src/data/stationViewData";
import { startPlaybackClock } from "../../src/lib/playback-clock";
import { usePlaybackStore } from "../../src/store/usePlaybackStore";

describe("playback clock", () => {
  let now = 0;
  let nextId = 0;
  let stop: () => void;
  const frames = new Map<number, FrameRequestCallback>();
  const state = () => usePlaybackStore.getState();
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
    state().loadData(stationViewData);
    stop = startPlaybackClock();
  });
  afterEach(() => { stop(); frames.clear(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });

  it("plays from the current position without duplicate loops", () => {
    state().seek(80);
    state().play();
    state().play();
    expect(frames.size).toBe(1);
    frameAt(1500);
    expect(state().currentTime_s).toBe(81.5);
    expect(frames.size).toBe(1);
  });
  it("settles the partial frame on pause, preserves snapshots, and resumes", () => {
    state().seek(85);
    state().play();
    now = 500;
    state().pause();
    expect(state().currentTime_s).toBe(85.5);
    expect(frames.size).toBe(0);
    const snapshot = state().snapshot();
    frameAt(10000);
    expect(state().snapshot()).toEqual(snapshot);
    state().play();
    frameAt(11000);
    expect(state().currentTime_s).toBe(86.5);
  });
  it("does not play without a run or beyond its end", () => {
    usePlaybackStore.setState({ data: null });
    state().play();
    expect(state().isPlaying).toBe(false);
    state().loadData(stationViewData);
    state().seek(359.9);
    state().play();
    frameAt(1000);
    expect(state().currentTime_s).toBe(360);
    expect(state().isPlaying).toBe(false);
    expect(frames.size).toBe(0);
    state().play();
    expect(state().isPlaying).toBe(false);
  });
  it("cleans up queued frames and freezes playback on unmount", () => {
    state().play();
    stop();
    expect(frames.size).toBe(0);
    frameAt(2000);
    expect(state().currentTime_s).toBe(0);
    expect(state().isPlaying).toBe(false);
  });
  it("rewinds a running run by 30 simulated seconds and rebuilds passenger positions", () => {
    state().seek(115);
    state().play();
    state().rewind30();
    expect(state().currentTime_s).toBe(85);
    expect(state().snapshot()?.passengers.find((passenger) => passenger.passenger_id === "p-001")?.position)
      .toEqual({ x: 389, y: 135 });
    expect(state().isPlaying).toBe(true);
    expect(frames.size).toBe(1);
    frameAt(1000);
    expect(state().currentTime_s).toBe(86);
  });
  it("rewinds paused and completed runs, clamping at the start", () => {
    state().seek(360);
    state().rewind30();
    expect(state().currentTime_s).toBe(330);
    expect(state().isPlaying).toBe(false);
    state().seek(10);
    state().rewind30();
    state().rewind30();
    expect(state().currentTime_s).toBe(0);
    expect(state().isPlaying).toBe(false);
  });
  it("includes elapsed time since the last frame when rewinding", () => {
    state().seek(100);
    state().play();
    now = 500;
    state().rewind30();
    expect(state().currentTime_s).toBe(70.5);
    frameAt(1000);
    expect(state().currentTime_s).toBe(71);
  });
});
