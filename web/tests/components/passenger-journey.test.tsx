// AI contribution: 50% or more AI-generated
// @vitest-environment jsdom
/** The followed passenger's readout under a Compare panel turns the journey into words (#239). */
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { act, cleanup, render, screen } from "@testing-library/react";
import { PassengerJourney } from "../../src/components/passenger-journey";
import { EMPTY_COMPARISON, useComparisonStore } from "../../src/store/useComparisonStore";
import { usePlaybackStore } from "../../src/store/usePlaybackStore";
import { JOURNEY_RUN } from "../fixtures/journeyRun";

/** Follow `passengerId` at `time_s` and return the readout's value for one row. */
function readout(passengerId: string, time_s: number, row: string) {
  act(() => {
    useComparisonStore.setState({ selectedPassengerId: passengerId });
    usePlaybackStore.setState({ currentTime_s: time_s });
  });
  return screen.getByText(row).nextSibling?.textContent;
}

beforeEach(() => {
  useComparisonStore.setState(EMPTY_COMPARISON);
  usePlaybackStore.setState({ currentTime_s: 0 });
});
afterEach(cleanup);

describe("PassengerJourney", () => {
  it("reads 'Made the connection' once p-001's train leaves at 175 s", () => {
    render(<PassengerJourney run={JOURNEY_RUN} />);
    expect(readout("p-001", 172, "Connection outcome")).toBe("Not decided yet");
    expect(readout("p-001", 175, "Connection outcome")).toBe("Made the connection");
    expect(readout("p-001", 175, "Where now")).toBe("Left the station");
  });

  it("names the missed train, then the extra wait once p-002 leaves at 250 s", () => {
    render(<PassengerJourney run={JOURNEY_RUN} />);
    expect(readout("p-002", 220, "Connection outcome")).toBe("Missed train metro-001");
    expect(readout("p-002", 240, "Train or connection")).toBe("Train metro-002");
    expect(readout("p-002", 250, "Connection outcome")).toBe("Missed train metro-001, left 1 min 15 s later");
  });

  // Edge: someone only in the other run, and nobody followed at all
  it("says 'Not in this run' for a missing passenger and draws nothing when nobody is followed", () => {
    const { container } = render(<PassengerJourney run={JOURNEY_RUN} />);
    expect(readout("nobody", 200, "Connection outcome")).toBe("Not in this run");

    act(() => useComparisonStore.setState({ selectedPassengerId: null }));
    expect(container.innerHTML).toBe("");
  });
});
