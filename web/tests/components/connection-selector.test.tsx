// AI contribution: 50% or more AI-generated
// @vitest-environment jsdom
/** Selection loads data atomically and rejects unknown connection identities. */
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { ConnectionSelector } from "../../src/components/connection-selector";
import { stationViewData } from "../../src/data/stationViewData";
import { usePlaybackStore } from "../../src/store/usePlaybackStore";

describe("ConnectionSelector", () => {
  const second = structuredClone(stationViewData);
  second.connections[0].id = "test-connection";
  second.connections[0].label = "Test connection";
  second.passenger_tracks.forEach((track) => { track.connection_id = "test-connection"; });
  beforeEach(() => {
    usePlaybackStore.getState().setAvailableRuns([stationViewData, second]);
    usePlaybackStore.getState().loadData(stationViewData);
  });
  afterEach(cleanup);
  it("loads the selected run, resets time and shows its active indicator", () => {
    usePlaybackStore.getState().seek(120);
    render(<ConnectionSelector />);
    fireEvent.click(screen.getByRole("button", { name: /Test connection/ }));
    expect(usePlaybackStore.getState().data).toBe(second);
    expect(usePlaybackStore.getState().currentTime_s).toBe(0);
    expect(screen.getByRole("button", { name: /Test connection/ }).getAttribute("aria-pressed")).toBe("true");
  });
  it("does not reset the already active connection", () => {
    usePlaybackStore.getState().seek(120);
    render(<ConnectionSelector />);
    fireEvent.click(screen.getByRole("button", { name: /McGill/ }));
    expect(usePlaybackStore.getState().currentTime_s).toBe(120);
  });
  it("rejects unavailable selections without losing the run", () => {
    expect(() => usePlaybackStore.getState().selectConnection("unknown")).toThrow("Unknown connection");
    expect(usePlaybackStore.getState().data).toBe(stationViewData);
    expect(() => usePlaybackStore.getState().setAvailableRuns([second, second])).toThrow("Duplicate connection");
  });
});
