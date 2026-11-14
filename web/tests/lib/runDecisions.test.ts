// AI contribution: 50% or more AI-generated
/** Reading a simulated run's hold decisions for the decision view (#57). */
import { describe, expect, it } from "vitest";
import { runDecisions } from "../../src/lib/runDecisions";

/** A hold record in the run endpoint's shape. */
const hold = (time_s: number, applied_s = 60) => ({
  time_s,
  train_id: "stm:T1",
  station_id: "32",
  platform_id: "green_mcgill_0",
  requested_s: 60,
  applied_s,
  reason: "headway_regulation",
});

describe("runDecisions", () => {
  it("returns the run's holds in time order with every printed field", () => {
    const decisions = runDecisions({ decisions: [hold(900), hold(270, 30)] });

    expect(decisions?.map((decision) => decision.time_s)).toEqual([270, 900]);
    expect(decisions?.[0]).toEqual(hold(270, 30));
  });

  it("keeps an empty list, which means the strategy never held a train", () => {
    expect(runDecisions({ decisions: [] })).toEqual([]);
  });

  it("returns null for a run with no decisions list, so mock playback can fall back", () => {
    expect(runDecisions({ duration_s: 3600 })).toBeNull();
    expect(runDecisions(null)).toBeNull();
    expect(runDecisions({ decisions: "none" })).toBeNull();
  });

  it("skips malformed records instead of dropping the whole list", () => {
    const decisions = runDecisions({
      decisions: [
        hold(120),
        { ...hold(240), applied_s: Number.NaN },
        { ...hold(300), train_id: 7 },
        { ...hold(360), reason: undefined },
        "not a record",
      ],
    });

    expect(decisions?.map((decision) => decision.time_s)).toEqual([120]);
  });
});
