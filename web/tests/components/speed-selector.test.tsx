// AI contribution: 50% or more AI-generated
// @vitest-environment jsdom
/** Speed UI updates shared playback without a parallel component state. */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { SpeedSelector } from "../../src/components/speed-selector";
import { stationViewData } from "../../src/data/stationViewData";
import { usePlaybackStore } from "../../src/store/usePlaybackStore";

describe("SpeedSelector", () => {
  beforeEach(() => {
    vi.spyOn(performance, "now").mockReturnValue(0);
    usePlaybackStore.getState().loadData(stationViewData);
  });
  afterEach(() => { cleanup(); vi.restoreAllMocks(); });
  it("renders exactly four supported speeds and indicates the active choice", () => {
    render(<SpeedSelector />);
    expect(screen.getAllByRole("button")).toHaveLength(4);
    for (const speed of [0.5, 1, 2, 10]) {
      const button = screen.getByRole("button", { name: `${speed}× speed` });
      fireEvent.click(button);
      expect(usePlaybackStore.getState().speed).toBe(speed);
      expect(button.getAttribute("aria-pressed")).toBe("true");
    }
  });
  it("keeps position and playing state when speed is selected", () => {
    usePlaybackStore.getState().seek(85);
    usePlaybackStore.getState().play();
    render(<SpeedSelector />);
    fireEvent.click(screen.getByRole("button", { name: "10× speed" }));
    expect(usePlaybackStore.getState().currentTime_s).toBe(85);
    expect(usePlaybackStore.getState().isPlaying).toBe(true);
  });
  it("disables every option without a loaded run", () => {
    usePlaybackStore.setState({ data: null });
    render(<SpeedSelector />);
    expect(screen.getAllByRole("button").every((button) => (button as HTMLButtonElement).disabled)).toBe(true);
  });
});
