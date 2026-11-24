// AI contribution: 50% or more AI-generated
/** Running hold and connection totals for one Compare panel (US-4.1, #230). */
import { describe, expect, it } from "vitest";
import { stationViewData } from "../../src/data/stationViewData";
import { comparisonStatsAt, formatDuration, timeChanges } from "../../src/lib/comparisonStats";
import type {
  PassengerOutcome, StationViewData, TrainMovementEvent,
} from "../../src/types/stationView";

const CONNECTION = "test-connection";
const TO_PLATFORM = "metro_p1";

function outcome(
  id: string,
  status: PassengerOutcome["status"],
  departure_s: number | null,
  missed_train_ids: string[] = [],
): PassengerOutcome {
  return {
    passenger_id: id, connection_id: CONNECTION, alighting_s: 0,
    platform_arrival_s: null, missed_train_ids, boarded_train_id: null,
    boarding_s: null, departure_s, transfer_time_s: null, delay_s: null, status,
  };
}

function departure(train_id: string, platform_id: string, time_s: number): TrainMovementEvent {
  return {
    event_type: "train_departure", train_id, station_id: "s", platform_id, time_s, scheduled_s: time_s,
  };
}

// Holds at 100 s (30 s long) and 200 s (10 s long). Train m1 leaves the
// transfer platform at 150 s and m2 at 250 s; m1 also leaves another
// platform at 50 s, which must not count. Passenger b misses m1 and boards
// m2; e misses m1 and never boards before the run ends. Both are missed
// from 150 s. Passenger d is still pending and never counts.
const RUN: StationViewData = {
  ...stationViewData,
  connections: [{
    id: CONNECTION, label: "Test", from_platform_id: "rem_p1",
    to_platform_id: TO_PLATFORM, corridor_id: "c",
  }],
  train_events: [
    departure("m1", "other_platform", 50),
    departure("m1", TO_PLATFORM, 150),
    departure("m2", TO_PLATFORM, 250),
  ],
  time_series: {
    start_s: 0, end_s: 360, bucket_s: 180, buckets: [],
    hold_events: [
      { time_s: 100, train_id: "t1", station_id: "s", platform_id: "p", applied_s: 30 },
      { time_s: 200, train_id: "t2", station_id: "s", platform_id: "p", applied_s: 10 },
    ],
  },
  passenger_outcomes: [
    outcome("a", "made", 130),
    outcome("b", "missed", 250, ["m1"]),
    outcome("c", "made", 210),
    outcome("d", "pending", null),
    outcome("e", "missed", null, ["m1"]),
  ],
};

describe("comparisonStatsAt", () => {
  it.each([
    // time, holding now, holds so far, made, missed
    [0, false, 0, 0, 0],
    [50, false, 0, 0, 0],
    [100, true, 1, 0, 0],
    [129.9, true, 1, 0, 0],
    [130, false, 1, 1, 0],
    [150, false, 1, 1, 2],
    [205, true, 2, 1, 2],
    [360, false, 2, 2, 2],
  ])("at %d s", (time, holdingNow, holds, made, missed) => {
    expect(comparisonStatsAt(RUN, time)).toEqual({ holdingNow, holds, made, missed });
  });

  it("uses the first departure of the missed train after the passenger alights", () => {
    // m1 leaves the transfer platform at 150 s and again at 300 s; alighting
    // at 200 s means the miss is the 300 s departure.
    const run: StationViewData = {
      ...RUN,
      train_events: [departure("m1", TO_PLATFORM, 150), departure("m1", TO_PLATFORM, 300)],
      passenger_outcomes: [{ ...outcome("f", "missed", null, ["m1"]), alighting_s: 200 }],
    };
    expect(comparisonStatsAt(run, 299).missed).toBe(0);
    expect(comparisonStatsAt(run, 300).missed).toBe(1);
  });

  it("counts zero for a run without a time series or outcomes", () => {
    expect(comparisonStatsAt(stationViewData, 200))
      .toEqual({ holdingNow: false, holds: 0, made: 0, missed: 0 });
  });
});

describe("timeChanges (US-4.3)", () => {
  it("mirrors the holding side's saved and lost time on the no-holding side", () => {
    const { holding, noHolding } = timeChanges({
      better_off: 45, worse_off: 2, unaffected: 1238, not_compared: 82,
      total_time_saved_s: 11490, total_time_lost_s: 100,
      average_time_saved_s: 255.33, average_time_lost_s: 50,
    });

    expect(holding).toEqual({ saved_s: 11490, savedPassengers: 45, lost_s: 100, lostPassengers: 2 });
    expect(noHolding).toEqual({ saved_s: 100, savedPassengers: 2, lost_s: 11490, lostPassengers: 45 });
  });
});

describe("formatDuration", () => {
  it.each([
    [0, "0 s"],
    [59.4, "59 s"],
    // Edge: 59.6 s rounds up into the minutes format
    [59.6, "1 min 0 s"],
    [255, "4 min 15 s"],
    [11490, "3 h 11 min"],
  ])("shows %s s as %s", (seconds, text) => {
    expect(formatDuration(seconds)).toBe(text);
  });
});
