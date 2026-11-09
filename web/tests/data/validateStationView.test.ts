// AI contribution: 50% or more AI-generated
import { describe, expect, it } from "vitest";
import { stationViewData } from "../../src/data/stationViewData";
import { parseStationViewData } from "../../src/lib/validateStationView";

describe("parseStationViewData", () => {
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
