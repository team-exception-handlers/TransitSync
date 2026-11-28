// AI contribution: 50% or more AI-generated
/** A run with hand-worked passenger outcomes, shared by the journey tests (#239). */
import { stationViewData } from "../../src/data/stationViewData";
import type { PassengerOutcome, StationViewData } from "../../src/types/stationView";

/** A pending outcome on the fixture's connection, alighting at 70 s, with the given fields. */
export function outcome(fields: Partial<PassengerOutcome> & Pick<PassengerOutcome, "passenger_id">): PassengerOutcome {
  return {
    connection_id: "mcgill-rem-green", alighting_s: 70, platform_arrival_s: null, missed_train_ids: [],
    boarded_train_id: null, boarding_s: null, departure_s: null, transfer_time_s: null,
    delay_s: null, status: "pending", ...fields,
  };
}

// In the shared fixture metro-001 leaves the green platform at 175 s and
// metro-002 at 250 s. p-001 walks from 70 s and boards at 170 s, so they make
// metro-001. p-002 walks from 78 s, queues at 130 s, waits from 210 s and
// boards at 235 s: here they miss metro-001 and leave on metro-002, so the
// miss cost them 250 - 175 = 75 s.
export const JOURNEY_RUN: StationViewData = {
  ...stationViewData,
  passenger_outcomes: [
    outcome({ passenger_id: "p-001", boarded_train_id: "metro-001", boarding_s: 170,
      departure_s: 175, delay_s: 0, status: "made" }),
    outcome({ passenger_id: "p-002", missed_train_ids: ["metro-001"], boarded_train_id: "metro-002",
      boarding_s: 235, departure_s: 250, delay_s: 75, status: "missed" }),
  ],
};
