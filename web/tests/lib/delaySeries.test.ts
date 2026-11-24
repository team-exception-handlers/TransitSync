// AI contribution: 50% or more AI-generated
/** Unit tests for chart bucket conversion and clutter-reduction markers. */
import { describe, expect, it } from "vitest";
import {
  delayChartPoints,
  holdEventMarkers,
  holdsForDelayBucket,
} from "../../src/lib/delaySeries";

describe("delayChartPoints", () => {
  it("maps 5-minute buckets to elapsed-axis points", () => {
    const points = delayChartPoints({
      start_s: 0,
      end_s: 600,
      bucket_s: 300,
      buckets: [
        { start_s: 0, end_s: 300, average_passenger_delay_s: 12.5, passenger_count: 4 },
        { start_s: 300, end_s: 600, average_passenger_delay_s: 20, passenger_count: 6 },
      ],
      hold_events: [],
    });

    expect(points.map((point) => [point.time_s, point.average_passenger_delay_s]))
      .toStrictEqual([[0, 12.5], [300, 20]]);
  });
});

describe("holdEventMarkers", () => {
  it("removes near-duplicate markers and sorts by simulation time", () => {
    const markers = holdEventMarkers([
      { time_s: 300, train_id: "T2", station_id: "32", platform_id: "P", applied_s: 20 },
      { time_s: 310, train_id: "T3", station_id: "32", platform_id: "P", applied_s: 20 },
      { time_s: 100, train_id: "T1", station_id: "32", platform_id: "P", applied_s: 20 },
    ]);

    expect(markers.map((event) => event.time_s)).toStrictEqual([100, 300]);
  });
});

describe("holdsForDelayBucket", () => {
  it("includes holds at the bucket start and excludes the next bucket boundary", () => {
    const holds = [
      { time_s: 300, train_id: "T1", station_id: "32", platform_id: "P", applied_s: 20 },
      { time_s: 599, train_id: "T2", station_id: "32", platform_id: "P", applied_s: 30 },
      { time_s: 600, train_id: "T3", station_id: "32", platform_id: "P", applied_s: 40 },
    ];

    expect(holdsForDelayBucket(holds, 300, 600).map((event) => event.train_id))
      .toStrictEqual(["T1", "T2"]);
  });
});
