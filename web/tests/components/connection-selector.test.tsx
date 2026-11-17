// AI contribution: 50% or more AI-generated
// @vitest-environment jsdom
/** Selection loads data atomically and rejects unknown connection identities. */
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { ConnectionSelector } from "../../src/components/connection-selector";
import { stationViewData } from "../../src/data/stationViewData";
import { usePlaybackStore } from "../../src/store/usePlaybackStore";
import { connectionRuns } from "../../src/data/connection-runs";
import { parseStationViewData } from "../../src/lib/validateStationView";

describe("ConnectionSelector", () => {
  const second = structuredClone(stationViewData);
  second.connections[0].id = "test-connection";
  second.connections[0].label = "Test connection";
  second.passenger_tracks.forEach((track) => { track.connection_id = "test-connection"; });

  // Re-parse second so its derived 'passengers' match the updated tracks
  const parsedSecond = parseStationViewData(second);

  beforeEach(() => {
    usePlaybackStore.getState().setAvailableRuns([stationViewData, parsedSecond]);
    usePlaybackStore.getState().loadData(stationViewData);
    // No test in this file exercises the backend catalog unless it sets one.
    usePlaybackStore.getState().setAvailableConnections(null);
  });
  afterEach(cleanup);
  it("loads the selected run, resets time and shows its active indicator", () => {
    usePlaybackStore.getState().seek(120);
    render(<ConnectionSelector />);
    fireEvent.click(screen.getByRole("button", { name: /Test connection/ }));
    expect(usePlaybackStore.getState().data).toStrictEqual(parsedSecond);
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
    expect(usePlaybackStore.getState().data).toStrictEqual(stationViewData);
    expect(() => usePlaybackStore.getState().setAvailableRuns([second, second])).toThrow("Duplicate connection");
  });
  it("marks exactly one connection as pressed and moves it when selection changes", () => {
    usePlaybackStore.getState().setAvailableRuns(connectionRuns);
    render(<ConnectionSelector />);
    const selected = screen.getByRole("button", { pressed: true });
    expect(screen.getAllByRole("button", { pressed: false })).toHaveLength(2);
    const next = screen.getAllByRole("button", { pressed: false })[0];
    fireEvent.click(next);
    expect(screen.getByRole("button", { pressed: true })).toBe(next);
    expect(selected.getAttribute("aria-pressed")).toBe("false");
    expect(screen.getAllByRole("button", { pressed: false })).toHaveLength(2);
  });
  it("keeps the visual selected indicator after a playback time change", () => {
    usePlaybackStore.getState().setAvailableRuns([stationViewData, second]);
    usePlaybackStore.getState().loadData(stationViewData);
    usePlaybackStore.getState().selectConnection("test-connection");
    render(<ConnectionSelector />);
    usePlaybackStore.getState().seek(45);
    const button = screen.getByRole("button", { name: /Test connection/ });
    expect(button.getAttribute("aria-pressed")).toBe("true");
  });
  it("lists all three documented connections with their metro line and switches data", () => {
    usePlaybackStore.getState().setAvailableRuns(connectionRuns);
    render(<ConnectionSelector />);
    expect(screen.getAllByRole("button")).toHaveLength(3);
    for (const [name, line, interchange] of [
      ["Gare Centrale", "orange", "gare_centrale_bonaventure"],
      ["McGill", "green", "mcgill"],
      ["Édouard-Montpetit", "blue", "edouard_montpetit"],
    ]) {
      const button = screen.getByRole("button", { name: new RegExp(`${name}.*${line} line`) });
      fireEvent.click(button);
      expect(usePlaybackStore.getState().data?.interchange.id).toBe(interchange);
      expect(button.getAttribute("aria-pressed")).toBe("true");
    }
  });

  it("renders from the backend connection catalog when one is set, keeping each metro line (#76)", () => {
    // availableRuns stays on the mock fixture: the catalog only drives what
    // is shown and selectable, not the run data behind each connection.
    usePlaybackStore.getState().setAvailableRuns(connectionRuns);
    usePlaybackStore.getState().setAvailableConnections([
      {
        id: "gare_centrale_bonaventure-rem-orange",
        label: "Gare Centrale Catalog",
        metro_line_id: "orange",
        interchange: { id: "gare_centrale_bonaventure", name: "Gare Centrale ↔ Bonaventure" },
      },
      {
        id: "mcgill-rem-green",
        label: "McGill Catalog",
        metro_line_id: "green",
        interchange: { id: "mcgill", name: "McGill" },
      },
      {
        id: "edouard_montpetit-rem-blue",
        label: "Édouard-Montpetit Catalog",
        metro_line_id: "blue",
        interchange: { id: "edouard_montpetit", name: "Édouard-Montpetit" },
      },
    ]);
    render(<ConnectionSelector />);

    expect(screen.getAllByRole("button")).toHaveLength(3);
    // Labels come from the catalog, not the fixture, proving the catalog drives display.
    const button = screen.getByRole("button", { name: /McGill Catalog.*green line/ });
    fireEvent.click(button);
    expect(usePlaybackStore.getState().selectedConnectionId).toBe("mcgill-rem-green");
    expect(button.getAttribute("aria-pressed")).toBe("true");
  });

  it("falls back to the run catalog when the backend connection list is unavailable", () => {
    usePlaybackStore.getState().setAvailableRuns(connectionRuns);
    usePlaybackStore.getState().setAvailableConnections(null);
    render(<ConnectionSelector />);

    // Labels come from the mock fixture (buildMockRun's labels), not a catalog entry.
    expect(screen.getByRole("button", { name: /McGill.*green line/ })).toBeDefined();
  });
});

