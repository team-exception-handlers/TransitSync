// AI contribution: 50% or more AI-generated
// @vitest-environment jsdom
/** End-to-end React/store/frame integration, without relying on real-time delays. */
import { StrictMode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import App from "../../src/App";
import { usePlaybackStore } from "../../src/store/usePlaybackStore";

describe("playback integration", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    const start = Date.now();
    vi.spyOn(performance, "now").mockImplementation(() => Date.now() - start);
    // Simulate 60-ish frames per second; timer counts expose duplicate loops.
    vi.stubGlobal("requestAnimationFrame", (callback: FrameRequestCallback) =>
      setTimeout(() => callback(performance.now()), 16));
    vi.stubGlobal("cancelAnimationFrame", clearTimeout);
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(null);
    usePlaybackStore.setState({ data: null, availableRuns: [], isPlaying: false, updatedAt_ms: null });
  });
  afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); vi.useRealTimers(); });

  it("keeps clock, slider, Canvas and controls synchronized through StrictMode and cleanup", () => {
    const view = render(<StrictMode><App /></StrictMode>);
    fireEvent.change(screen.getByRole("slider"), { target: { value: "85" } });
    fireEvent.click(screen.getByRole("button", { name: "Play" }));
    expect(vi.getTimerCount()).toBe(1);
    act(() => vi.advanceTimersByTime(1008));
    expect(usePlaybackStore.getState().currentTime_s).toBeCloseTo(86.008);
    expect(screen.getAllByText("07:41:26")).toHaveLength(2);
    expect(screen.getByRole("img").getAttribute("aria-label")).toContain("86.0");
    fireEvent.click(screen.getByRole("button", { name: "Pause" }));
    const time = usePlaybackStore.getState().currentTime_s;
    act(() => vi.advanceTimersByTime(1008));
    expect(usePlaybackStore.getState().currentTime_s).toBe(time);
    fireEvent.click(screen.getByRole("button", { name: "Rewind 30 seconds" }));
    expect(usePlaybackStore.getState().currentTime_s).toBeCloseTo(56.008);
    fireEvent.click(screen.getByRole("button", { name: "Play" }));
    fireEvent.click(screen.getByRole("button", { name: /Gare Centrale/ }));
    expect(usePlaybackStore.getState().currentTime_s).toBe(0);
    expect(screen.getByRole("img").getAttribute("aria-label")).toContain("Gare Centrale");
    expect(vi.getTimerCount()).toBe(0);
    fireEvent.click(screen.getByRole("button", { name: "Play" }));
    view.unmount();
    expect(vi.getTimerCount()).toBe(0);
    expect(usePlaybackStore.getState().isPlaying).toBe(false);
  });
});
