// AI contribution: 50% or more AI-generated
/** Running hold and connection totals for one Compare panel (US-4.1, #230). */
import { describe, expect, it } from "vitest";
import { stationViewData } from "../../src/data/stationViewData";
import { comparisonStatsAt, formatDuration, splitAt } from "../../src/lib/comparisonStats";
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

describe("splitAt (US-4.3)", () => {
  // D = departure with holding - departure without, threshold 30 s.
  // a: 100 s vs 300 s (D -200, better off). b: 400 s vs 350 s (D +50, worse
  // off). c: 500 s vs 510 s (D -10, unaffected). d leaves in neither run.
  // e is in the holding run only.
  const run = (departures: [string, number | null][]): StationViewData => ({
    ...stationViewData,
    passenger_outcomes: departures.map(([id, time]) => outcome(id, time === null ? "pending" : "made", time)),
  });
  const PAIR = {
    holding: run([["a", 100], ["b", 400], ["c", 500], ["d", null], ["e", 50]]),
    noHolding: run([["a", 300], ["b", 350], ["c", 510], ["d", null]]),
    threshold_s: 30,
  };

  it("compares everyone at the run end and mirrors the no-holding side", () => {
    const split = splitAt(PAIR, 600);

    expect(split.holding).toEqual({ saved_s: 200, savedPassengers: 1, lost_s: 50, lostPassengers: 1 });
    expect(split.noHolding).toEqual({ saved_s: 50, savedPassengers: 1, lost_s: 200, lostPassengers: 1 });
    expect(split.unaffected).toBe(1);
    // d left in neither run and e is in one run only
    expect(split.notCompared).toBe(2);
    // Net over every compared passenger, unaffected ones too: -200 + 50 - 10
    expect(split.net_s).toBe(-160);
  });

  it("builds up during playback, using the current time for a run not left yet", () => {
    // Nobody has left at 0 s
    expect(splitAt(PAIR, 0).holding).toEqual({ saved_s: 0, savedPassengers: 0, lost_s: 0, lostPassengers: 0 });
    expect(splitAt(PAIR, 0).notCompared).toBe(5);
    // At 120 s a has left with holding only: D = 100 - 120 = -20, unaffected so far
    expect(splitAt(PAIR, 120).unaffected).toBe(1);
    // At 200 s: D = 100 - 200 = -100, better off by at least 100 s
    expect(splitAt(PAIR, 200).holding.saved_s).toBe(100);
  });
});

describe("formatDuration", () => {
  it.each([
    [0, "0 s"],
    [59.4, "59 s"],
    // Edge: 59.6 s rounds up into the minutes format
    [59.6, "1 min 0 s"],
    [255, "4 min 15 s"],
    // Hours round to the nearest minute, like seconds round: 3 h 11 min 30 s
    [11490, "3 h 12 min"],
    [5399.6, "1 h 30 min"],
    [3599.6, "1 h 0 min"],
  ])("shows %s s as %s", (seconds, text) => {
    expect(formatDuration(seconds)).toBe(text);
  });
});
