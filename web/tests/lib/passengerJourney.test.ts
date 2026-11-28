// AI contribution: 50% or more AI-generated
/** journeyAt says where the followed passenger is and how their connection went, as playback runs (#239). */
import { describe, expect, it } from "vitest";
import { stationViewData } from "../../src/data/stationViewData";
import { comparisonStatsAt } from "../../src/lib/comparisonStats";
import { journeyAt } from "../../src/lib/passengerJourney";
import type { StationViewData } from "../../src/types/stationView";
import { JOURNEY_RUN as RUN, outcome } from "../fixtures/journeyRun";

const OPEN = { kind: "open" };
const MISSED = { kind: "missed", trainId: "metro-001", delay_s: null };

describe("journeyAt", () => {
  it.each([
    [50, "arriving", OPEN],
    [100, "walking", OPEN],
    [140, "queued", OPEN],
    // metro-001 has left without them while they are still walking
    [175, "walking", MISSED],
    [220, "waiting", MISSED],
  ])("at %s s a passenger who misses is %s", (time, where, result) => {
    const journey = journeyAt(RUN, "p-002", time);
    expect(journey.where).toBe(where);
    expect(journey.outcome).toEqual(result);
    expect(journey.connectionLabel).toBe("McGill");
  });

  it("names the later train once boarded and the extra wait once it leaves", () => {
    expect(journeyAt(RUN, "p-002", 240)).toMatchObject({ where: "onboard", trainId: "metro-002", outcome: MISSED });
    expect(journeyAt(RUN, "p-002", 250)).toMatchObject({
      where: "left", trainId: "metro-002", outcome: { kind: "missed", trainId: "metro-001", delay_s: 75 },
    });
  });

  it("shows a made connection only when the train leaves with them", () => {
    expect(journeyAt(RUN, "p-001", 172)).toMatchObject({ where: "onboard", trainId: "metro-001", outcome: OPEN });
    expect(journeyAt(RUN, "p-001", 175)).toMatchObject({ where: "left", outcome: { kind: "made" } });
  });

  it("goes back to the earlier state on a backwards seek", () => {
    journeyAt(RUN, "p-002", 250);
    expect(journeyAt(RUN, "p-002", 100)).toMatchObject({ where: "walking", outcome: OPEN, trainId: null });
  });

  // Edge (review on #432): the readout checks status as the panel's counts do,
  // so an outcome the panel does not count is never shown as decided
  it("agrees with the panel's made and missed counts, even for a pending outcome", () => {
    const run: StationViewData = {
      ...RUN,
      passenger_outcomes: [...(RUN.passenger_outcomes ?? []), outcome({
        passenger_id: "p-003", missed_train_ids: ["metro-001"], boarded_train_id: "metro-002",
        boarding_s: 235, departure_s: 250,
      })],
    };
    for (const time of [100, 175, 250]) {
      const kinds = ["p-001", "p-002", "p-003"].map((id) => journeyAt(run, id, time).outcome.kind);
      const stats = comparisonStatsAt(run, time);
      expect(kinds.filter((kind) => kind === "made").length).toBe(stats.made);
      expect(kinds.filter((kind) => kind === "missed").length).toBe(stats.missed);
    }
    expect(journeyAt(run, "p-003", 250).outcome).toEqual(OPEN);
  });

  // Edge: the passenger is only in the other run of the pair
  it("reports a passenger this run does not have as absent", () => {
    expect(journeyAt(RUN, "nobody", 200)).toEqual({
      where: "absent", connectionLabel: null, trainId: null, outcome: OPEN,
    });
  });

  // Edge: mock runs have tracks but no outcomes, so only the track is known
  it("falls back to the track when the run has no outcomes", () => {
    expect(journeyAt(stationViewData, "p-001", 170)).toMatchObject({
      where: "onboard", trainId: null, outcome: OPEN,
    });
  });
});
