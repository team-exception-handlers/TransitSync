// AI contribution: 50% or more AI-generated
/** Fake frames and a monotonic clock make playback tests independent of wall time. */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { stationViewData } from "../../src/data/stationViewData";
import { startPlaybackClock } from "../../src/lib/playback-clock";
import { usePlaybackStore } from "../../src/store/usePlaybackStore";
import { connectionRuns } from "../../src/data/connection-runs";

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
  it("shares one frame across multiple consumers and makes cleanup idempotent", () => {
    const releaseSecond = startPlaybackClock();
    state().play();
    expect(frames.size).toBe(1);
    releaseSecond();
    releaseSecond();
    frameAt(1000);
    expect(state().currentTime_s).toBe(1);
    expect(frames.size).toBe(1);
  });
  it("reanchors running seeks and stops on connection or run replacement", () => {
    state().setAvailableRuns(connectionRuns);
    state().play();
    now = 500;
    state().seek(85);
    frameAt(1000);
    expect(state().currentTime_s).toBe(85.5);
    state().selectConnection(connectionRuns[0].connections[0].id);
    expect(state().currentTime_s).toBe(0);
    expect(state().isPlaying).toBe(false);
    expect(frames.size).toBe(0);
    state().play();
    state().loadData(stationViewData);
    expect(state().isPlaying).toBe(false);
    expect(frames.size).toBe(0);
  });
  it("rejects bad input atomically while a valid run is playing", () => {
    state().play();
    expect(() => state().loadData({})).toThrow();
    expect(() => state().selectConnection("unavailable")).toThrow("Unknown connection");
    expect(state().isPlaying).toBe(true);
    expect(frames.size).toBe(1);
    frameAt(1000);
    expect(state().currentTime_s).toBe(1);
  });
  it.each([0.5, 1, 2, 10])("scales elapsed wall time by %s without changing recorded results", (speed) => {
    const original = structuredClone(stationViewData);
    state().setSpeed(speed);
    state().play();
    frameAt(85000 / speed);
    expect(state().currentTime_s).toBeCloseTo(85);
    expect(state().snapshot()).toEqual(state().getSnapshotAt(85));
    expect(stationViewData).toEqual(original);
  });
  it("changes speed mid-frame at the old rate without interrupting playback", () => {
    state().play();
    now = 500;
    state().setSpeed(10);
    expect(state().currentTime_s).toBe(0.5);
    expect(state().isPlaying).toBe(true);
    expect(frames.size).toBe(1);
    frameAt(1000);
    expect(state().currentTime_s).toBe(5.5);
  });
  it("remembers a speed chosen while paused and preserves it across connections", () => {
    state().seek(80);
    state().setSpeed(2);
    frameAt(5000);
    expect(state().currentTime_s).toBe(80);
    state().play();
    frameAt(6000);
    expect(state().currentTime_s).toBe(82);
    state().setAvailableRuns(connectionRuns);
    state().selectConnection(connectionRuns[0].connections[0].id);
    expect(state().speed).toBe(2);
    expect(state().currentTime_s).toBe(0);
  });
  it.each([0, -1, 3, NaN, Infinity])("rejects unsupported speed %s atomically", (speed) => {
    state().play();
    expect(() => state().setSpeed(speed)).toThrow("Unsupported playback speed");
    expect(state().speed).toBe(1);
    expect(state().isPlaying).toBe(true);
    expect(frames.size).toBe(1);
  });
  it.each([0.5, 1, 2, 10])("keeps exact elapsed-time scaling across irregular frames at %s×", (speed) => {
    state().seek(80);
    state().setSpeed(speed);
    state().play();
    for (const timestamp of [0.1, 16.67, 58.2, 273.9, 1000.001]) frameAt(timestamp);
    expect(state().currentTime_s).toBe(80 + 1.000001 * speed);
    // Dense frame delivery and a single delayed frame give the same position.
    const densePosition = state().currentTime_s;
    state().pause();
    state().seek(80);
    state().play();
    frameAt(2000.002);
    expect(state().currentTime_s).toBe(densePosition);
  });
  it.each([0.5, 1, 2, 10])("preserves pause/resume/rewind and end boundaries at %s×", (speed) => {
    state().seek(100);
    state().setSpeed(speed);
    state().play();
    frameAt(1000);
    state().pause();
    const paused = 100 + speed;
    expect(state().currentTime_s).toBe(paused);
    frameAt(10000);
    state().rewind30();
    expect(state().currentTime_s).toBe(paused - 30);
    state().play();
    frameAt(11000);
    expect(state().currentTime_s).toBe(paused - 30 + speed);
    state().seek(359.99);
    frameAt(12000);
    expect(state().currentTime_s).toBe(360);
    expect(state().isPlaying).toBe(false);
    expect(frames.size).toBe(0);
  });
  it("handles multiple speed changes inside a single frame without lost time", () => {
    state().play();
    now = 100;
    state().setSpeed(10);
    now = 150;
    state().setSpeed(0.5);
    frameAt(350);
    expect(state().currentTime_s).toBeCloseTo(0.7);
    expect(frames.size).toBe(1);
    state().setSpeed(0.5);
    expect(frames.size).toBe(1);
  });
  it("cannot start a zero-duration run or rewind an unloaded run", () => {
    state().loadData({ ...stationViewData, duration_s: 0, passenger_tracks: [], train_events: [] });
    state().play();
    expect(state().isPlaying).toBe(false);
    expect(frames.size).toBe(0);
    usePlaybackStore.setState({ data: null });
    state().rewind30();
    expect(state().currentTime_s).toBe(0);
  });
});
