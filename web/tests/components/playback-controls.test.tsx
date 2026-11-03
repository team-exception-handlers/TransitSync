// AI contribution: 50% or more AI-generated
// @vitest-environment jsdom
/** Button feedback and enabled state always follow the authoritative store. */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, act } from "@testing-library/react";
import { PlaybackControls } from "../../src/components/playback-controls";
import { stationViewData } from "../../src/data/stationViewData";
import { usePlaybackStore } from "../../src/store/usePlaybackStore";

describe("PlaybackControls", () => {
  beforeEach(() => {
    vi.spyOn(performance, "now").mockReturnValue(0);
    usePlaybackStore.getState().loadData(stationViewData);
  });
  afterEach(() => { cleanup(); vi.restoreAllMocks(); });
  it("starts and pauses actual playback with matching button feedback", () => {
    render(<PlaybackControls />);
    fireEvent.click(screen.getByRole("button", { name: "Play" }));
    expect(usePlaybackStore.getState().isPlaying).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "Pause" }));
    expect(usePlaybackStore.getState().isPlaying).toBe(false);
    expect(screen.getByRole("button", { name: "Play" })).toBeDefined();
  });
  it("disables Play without a run or at its end", () => {
    usePlaybackStore.setState({ data: null });
    render(<PlaybackControls />);
    expect((screen.getByRole("button", { name: "Play" }) as HTMLButtonElement).disabled).toBe(true);
    act(() => {
      usePlaybackStore.getState().loadData(stationViewData);
      usePlaybackStore.getState().seek(360);
    });
    expect((screen.getByRole("button", { name: "Play" }) as HTMLButtonElement).disabled).toBe(true);
  });
});
