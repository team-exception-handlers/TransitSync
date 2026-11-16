// AI contribution: 50% or more AI-generated
/** Reading a simulated run's hold decisions (#57) and their estimates (#39). */
import { describe, expect, it } from "vitest";
import { runDecisions, runEstimates } from "../../src/lib/runDecisions";

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

/** An estimates record in the run endpoint's shape, cut to the held train. */
const estimate = (time_s: number) => ({
  time_s,
  train_id: "stm:T1",
  station_id: "32",
  platform_id: "green_mcgill_0",
  trains: [
    {
      train_id: "stm:T1",
      predicted_arrival_s: { seen: null, true: null },
      onboard_load: { seen: 249, true: 394 },
    },
  ],
  transfers: [
    {
      group_id: "G1",
      passenger_count: { seen: 38, true: 42 },
      group_size: { seen: 54, true: 60 },
    },
  ],
});

describe("runEstimates", () => {
  it("returns each record with its seen and true values, nulls included", () => {
    expect(runEstimates({ estimates: [estimate(270)] })).toEqual([estimate(270)]);
  });

  it("returns null without an estimates list and keeps an empty one", () => {
    expect(runEstimates({ decisions: [] })).toBeNull();
    expect(runEstimates({ estimates: [] })).toEqual([]);
  });

  it("drops unusable records and values but keeps the rest of a record", () => {
    const [kept] = runEstimates({
      estimates: [
        { ...estimate(120), time_s: "120" },
        {
          ...estimate(270),
          trains: [{ train_id: "stm:T1", onboard_load: { seen: 1, true: Number.NaN } }],
          transfers: [...estimate(270).transfers, { group_id: 7 }],
        },
      ],
    }) ?? [];

    expect(kept.time_s).toBe(270);
    expect(kept.trains).toEqual([]);
    expect(kept.transfers).toEqual(estimate(270).transfers);
  });
});
