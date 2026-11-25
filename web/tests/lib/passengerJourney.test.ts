// AI contribution: 50% or more AI-generated
/** journeyAt says where the followed passenger is and how their connection went, as playback runs (#239). */
import { describe, expect, it } from "vitest";
import { stationViewData } from "../../src/data/stationViewData";
import { journeyAt } from "../../src/lib/passengerJourney";
import type { PassengerOutcome, StationViewData } from "../../src/types/stationView";

const CONNECTION = "mcgill-rem-green";

function outcome(fields: Partial<PassengerOutcome> & Pick<PassengerOutcome, "passenger_id">): PassengerOutcome {
  return {
    connection_id: CONNECTION, alighting_s: 70, platform_arrival_s: null, missed_train_ids: [],
    boarded_train_id: null, boarding_s: null, departure_s: null, transfer_time_s: null,
    delay_s: null, status: "pending", ...fields,
  };
}

// In the shared fixture metro-001 leaves the green platform at 175 s and
// metro-002 at 250 s. p-001 walks from 70 s and boards at 170 s, so they make
// metro-001. p-002 walks from 78 s, queues at 130 s, waits from 210 s and
// boards at 235 s: here they miss metro-001 and leave on metro-002, so the
// miss cost them 250 - 175 = 75 s.
const RUN: StationViewData = {
  ...stationViewData,
  passenger_outcomes: [
    outcome({ passenger_id: "p-001", boarded_train_id: "metro-001", boarding_s: 170,
      departure_s: 175, delay_s: 0, status: "made" }),
    outcome({ passenger_id: "p-002", missed_train_ids: ["metro-001"], boarded_train_id: "metro-002",
      boarding_s: 235, departure_s: 250, delay_s: 75, status: "missed" }),
  ],
};

describe("journeyAt", () => {
  it.each([
    [50, "arriving", null, null],
    [100, "walking", null, null],
    [140, "queued", null, null],
    // metro-001 has left without them while they are still walking
    [175, "walking", "missed", "metro-001"],
    [220, "waiting", "missed", "metro-001"],
  ])("at %s s a passenger who misses is %s", (time, where, result, missedTrain) => {
    const journey = journeyAt(RUN, "p-002", time);
    expect(journey.where).toBe(where);
    expect(journey.outcome).toBe(result);
    expect(journey.missedTrainId).toBe(missedTrain);
    expect(journey.connectionLabel).toBe("McGill");
  });

  it("names the later train once boarded and the extra wait once it leaves", () => {
    expect(journeyAt(RUN, "p-002", 240)).toMatchObject({ where: "onboard", trainId: "metro-002", delay_s: null });
    expect(journeyAt(RUN, "p-002", 250)).toMatchObject({
      where: "left", trainId: "metro-002", outcome: "missed", delay_s: 75,
    });
  });

  it("shows a made connection only when the train leaves with them", () => {
    expect(journeyAt(RUN, "p-001", 172)).toMatchObject({ where: "onboard", trainId: "metro-001", outcome: null });
    expect(journeyAt(RUN, "p-001", 175)).toMatchObject({ where: "left", outcome: "made", missedTrainId: null });
  });

  it("goes back to the earlier state on a backwards seek", () => {
    journeyAt(RUN, "p-002", 250);
    expect(journeyAt(RUN, "p-002", 100)).toMatchObject({ where: "walking", outcome: null, trainId: null });
  });

  // Edge: the passenger is only in the other run of the pair
  it("reports a passenger this run does not have as absent", () => {
    expect(journeyAt(RUN, "nobody", 200)).toEqual({
      where: "absent", connectionLabel: null, trainId: null,
      outcome: null, missedTrainId: null, delay_s: null,
    });
  });

  // Edge: mock runs have tracks but no outcomes, so only the track is known
  it("falls back to the track when the run has no outcomes", () => {
    expect(journeyAt(stationViewData, "p-001", 170)).toMatchObject({
      where: "onboard", trainId: null, outcome: null,
    });
  });
});
