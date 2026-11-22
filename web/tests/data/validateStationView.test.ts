// AI contribution: 50% or more AI-generated
import { describe, expect, it } from "vitest";
import { stationViewData } from "../../src/data/stationViewData";
import { parseStationViewData } from "../../src/lib/validateStationView";

describe("parseStationViewData", () => {
    it("keeps the results ID and rejects malformed IDs", () => {
        const run_id = "abc0".repeat(16);
        expect(parseStationViewData({ ...stationViewData, run_id }).run_id).toBe(run_id);
        expect(() => parseStationViewData({ ...stationViewData, run_id: "mcgill" }))
            .toThrow("Invalid simulation run ID");
    });

    const metrics = {
        total_affected_passengers: 3, successful_connections: 0, missed_connections: 1,
        average_transfer_time_s: 12.5, average_passenger_delay_s: null,
    };

    it("accepts optional metrics with pending passengers and an unknown average", () => {
        expect(parseStationViewData(stationViewData).passenger_metrics).toBeUndefined();
        expect(parseStationViewData({ ...stationViewData, passenger_metrics: metrics }).passenger_metrics)
            .toEqual(metrics);
    });

    it.each([
        null, [], {}, { ...metrics, total_affected_passengers: "3" },
        { ...metrics, successful_connections: -1 }, { ...metrics, missed_connections: 0.5 },
        { ...metrics, missed_connections: 4 }, { ...metrics, average_transfer_time_s: -2 },
        { ...metrics, average_passenger_delay_s: Infinity }, { ...metrics, average_transfer_time_s: undefined },
    ])("rejects malformed passenger metrics %#", (value) => {
        expect(() => parseStationViewData({ ...stationViewData, passenger_metrics: value }))
            .toThrow("Invalid passenger metrics");
    });

    it("keeps unfinished passenger outcomes and rejects duplicates", () => {
        const { passenger_id, connection_id } = stationViewData.passenger_tracks[0];
        const outcome = {
            passenger_id, connection_id, alighting_s: 0, platform_arrival_s: null,
            missed_train_ids: [], boarded_train_id: null, boarding_s: null,
            departure_s: null, transfer_time_s: null, delay_s: null, status: "pending",
        };
        const run = { ...stationViewData, passenger_outcomes: [outcome] };
        expect(parseStationViewData(run).passenger_outcomes).toEqual([outcome]);
        expect(() => parseStationViewData({ ...run, passenger_outcomes: [outcome, outcome] }))
            .toThrow("duplicate passenger outcome");
    });

    it("accepts valid station-view data", () => {
        const result = parseStationViewData(stationViewData);
        expect(result.interchange.id).toBe("mcgill");
        expect(result.platforms).toHaveLength(4);
    });

    it("rejects an unsupported schema version", () => {
        const invalidData = {
            ...stationViewData,
            schema_version: 99,
        };

        expect(() =>
            parseStationViewData(invalidData)
        ).toThrow("Unsupported station view schema version");
    });

    it("rejects a negative simulation duration", () => {
        const invalidData = {
            ...stationViewData,
            duration_s: -10,
        };

        expect(() =>
            parseStationViewData(invalidData)
        ).toThrow("Invalid simulation time metadata");
    });

    it("rejects invalid map dimensions", () => {
        const invalidData = structuredClone(stationViewData);
        invalidData.map.width = 0;

        expect(() =>
            parseStationViewData(invalidData)
        ).toThrow("Invalid map dimensions");
    });

    it("rejects duplicate platform IDs", () => {
        const invalidData = structuredClone(stationViewData);
        invalidData.platforms.push({
            ...invalidData.platforms[0],
        });

        expect(() =>
            parseStationViewData(invalidData)
        ).toThrow("Duplicate platform");
    });

    it("rejects nonnumeric passenger coordinates", () => {
        const invalidData = structuredClone(stationViewData);
        invalidData.passenger_tracks[0].samples[0].position.x = Number.NaN;

        expect(() =>
            parseStationViewData(invalidData)
        ).toThrow("Invalid passenger samples");
    });

    it("rejects passenger samples in the wrong order", () => {
        const invalidData = structuredClone(stationViewData);

        invalidData.passenger_tracks[0].samples[1].time_s = 50;

        expect(() =>
            parseStationViewData(invalidData)
        ).toThrow("Invalid passenger samples");
    });

    it("rejects passenger samples beyond the run duration", () => {
        const invalidData = structuredClone(stationViewData);

        invalidData.passenger_tracks[0].samples[0].time_s = 9999;

        expect(() =>
            parseStationViewData(invalidData)
        ).toThrow("Invalid passenger samples");
    });

    it("rejects unknown passenger connections", () => {
        const invalidData = structuredClone(stationViewData);

        invalidData.passenger_tracks[0].connection_id =
            "nonexistent_connection";

        expect(() =>
            parseStationViewData(invalidData)
        ).toThrow("Invalid passenger track");
    });

    it("rejects train events with unknown platform IDs", () => {
        const invalidData = structuredClone(stationViewData);

        invalidData.train_events[0].platform_id =
            "unknown_platform";

        expect(() =>
            parseStationViewData(invalidData)
        ).toThrow("Invalid train event");
    });

    it("rejects inconsistent train station IDs", () => {
        const invalidData = structuredClone(stationViewData);

        invalidData.train_events[0].station_id =
            "incorrect_station";

        expect(() =>
            parseStationViewData(invalidData)
        ).toThrow("Station/stop mismatch");
    });

    it("derives and populates passenger movements upon validation", () => {
        const result = parseStationViewData(stationViewData);
        expect(result.passengers).toBeDefined();
        expect(Array.isArray(result.passengers)).toBe(true);
    });
});

describe("parseStationViewData input checks", () => {
    type Data = typeof stationViewData;
    // Each case breaks one part of a valid copy of the McGill data and expects
    // the exact error. Cases are in the order the checks run.
    const cases: [string, (data: Data) => unknown, string][] = [
        ["a non-object", () => null, "Station view data must be an object"],
        [
            "a missing interchange name",
            (data) => ({ ...data, interchange: { id: "mcgill" } }),
            "Invalid interchange",
        ],
        [
            "a collection that is not a list",
            (data) => ({ ...data, corridors: {} }),
            "Invalid station view collections",
        ],
        [
            "a station without a position",
            (data) => {
                data.stations[0] = { ...data.stations[0], position: { x: 1 } as never };
                return data;
            },
            "Invalid station",
        ],
        [
            "a repeated station",
            (data) => ({ ...data, stations: [...data.stations, data.stations[0]] }),
            "Duplicate station: rem_mcgill",
        ],
        [
            "a platform on an unknown station",
            (data) => {
                data.platforms[0] = { ...data.platforms[0], station_id: "nowhere" };
                return data;
            },
            "Invalid platform",
        ],
        [
            "a corridor with a one-point path",
            (data) => {
                data.corridors[0] = { ...data.corridors[0], path: [data.corridors[0].path[0]] };
                return data;
            },
            "Invalid corridor: mcgill_rem_green_transfer",
        ],
        [
            "a repeated corridor",
            (data) => ({ ...data, corridors: [...data.corridors, data.corridors[0]] }),
            "Duplicate corridor: mcgill_rem_green_transfer",
        ],
        [
            "a connection on an unknown corridor",
            (data) => {
                data.connections[0] = { ...data.connections[0], corridor_id: "nowhere" };
                return data;
            },
            "Invalid connection: mcgill-rem-green",
        ],
        [
            "a repeated connection",
            (data) => ({ ...data, connections: [...data.connections, data.connections[0]] }),
            "Duplicate connection: mcgill-rem-green",
        ],
        [
            "a repeated passenger",
            (data) => ({
                ...data,
                passenger_tracks: [...data.passenger_tracks, data.passenger_tracks[0]],
            }),
            "Duplicate passenger: p-001",
        ],
    ];

    it.each(cases)("rejects %s", (_label, breakData, message) => {
        const invalid = breakData(structuredClone(stationViewData));
        // An Error argument makes Vitest compare the whole message exactly.
        expect(() => parseStationViewData(invalid)).toThrow(new Error(message));
    });
});
