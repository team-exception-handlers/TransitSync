// AI contribution: 50% or more AI-generated
/** Running hold and connection totals for one Compare panel (US-4.1, #230). */
import { describe, expect, it } from "vitest";
import { stationViewData } from "../../src/data/stationViewData";
import { comparisonStatsAt } from "../../src/lib/comparisonStats";
import type { PassengerOutcome, StationViewData } from "../../src/types/stationView";

function outcome(id: string, status: PassengerOutcome["status"], departure_s: number | null): PassengerOutcome {
  return {
    passenger_id: id, connection_id: "mcgill-rem-green", alighting_s: 0,
    platform_arrival_s: null, missed_train_ids: [], boarded_train_id: null,
    boarding_s: null, departure_s, transfer_time_s: null, delay_s: null, status,
  };
}

// Holds at 100 s (30 s long) and 200 s (10 s long); three decided passengers and one pending.
const RUN: StationViewData = {
  ...stationViewData,
  time_series: {
    start_s: 0, end_s: 360, bucket_s: 180, buckets: [],
    hold_events: [
      { time_s: 100, train_id: "t1", station_id: "s", platform_id: "p", applied_s: 30 },
      { time_s: 200, train_id: "t2", station_id: "s", platform_id: "p", applied_s: 10 },
    ],
  },
  passenger_outcomes: [
    outcome("a", "made", 130),
    outcome("b", "missed", 150),
    outcome("c", "made", 210),
    outcome("d", "pending", null),
  ],
};

describe("comparisonStatsAt", () => {
  it.each([
    // time, holding now, holds so far, made, missed
    [0, false, 0, 0, 0],
    [100, true, 1, 0, 0],
    [129.9, true, 1, 0, 0],
    [130, false, 1, 1, 0],
    [150, false, 1, 1, 1],
    [205, true, 2, 1, 1],
    [360, false, 2, 2, 1],
  ])("at %d s", (time, holdingNow, holds, made, missed) => {
    expect(comparisonStatsAt(RUN, time)).toEqual({ holdingNow, holds, made, missed });
  });

  it("counts zero for a run without a time series or outcomes", () => {
    expect(comparisonStatsAt(stationViewData, 200))
      .toEqual({ holdingNow: false, holds: 0, made: 0, missed: 0 });
  });
});
