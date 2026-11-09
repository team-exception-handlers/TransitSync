// AI contribution: 50% or more AI-generated

import { describe, expect, it } from "vitest";
import rawMapping from "../../src/data/interchange_mapping.json";
import rawMock from "../../src/data/mock-interchange.json";
import { buildStationViewData } from "../../src/lib/buildStationViewData";

import type { InterchangeMapping, MockInterchangeData } from "../../src/types/stationView";

const mapping = rawMapping as unknown as InterchangeMapping;
const mock = rawMock as unknown as MockInterchangeData;

describe("buildStationViewData", () => {
    const data = buildStationViewData(mapping, mock);

    it("loads the McGill interchange", () => {
        expect(data.interchange.id).toBe("mcgill");
        expect(data.interchange.name).toContain("McGill");
    });

    it("loads all four McGill platforms", () => {
        const platformIds = data.platforms.map(
            (platform) => platform.platform_id
        );

        expect(platformIds).toHaveLength(4);

        expect(platformIds).toEqual(
            expect.arrayContaining([
                "rem_mcgill_0",
                "rem_mcgill_1",
                "green_mcgill_0",
                "green_mcgill_1",
            ])
        );
    });

    it("preserves backend direction information", () => {
        const remPlatform = data.platforms.find(
            (platform) =>
                platform.platform_id === "rem_mcgill_1"
        );

        const metroPlatform = data.platforms.find(
            (platform) =>
                platform.platform_id === "green_mcgill_0"
        );

        expect(remPlatform?.direction_label).toBe(
            "Brossard"
        );

        expect(metroPlatform?.direction_label).toBe(
            "Honoré-Beaugrand"
        );
    });

    it("preserves backend stop and route IDs", () => {
        const platform = data.platforms.find(
            (platform) =>
                platform.platform_id === "green_mcgill_0"
        );

        expect(platform?.stop_id).toBe("32");
        expect(platform?.route_ids).toEqual(["1"]);
    });

    it("preserves the source feed identifiers", () => {
        const remPlatform = data.platforms.find(
            (platform) =>
                platform.platform_id === "rem_mcgill_0"
        );

        const metroPlatform = data.platforms.find(
            (platform) =>
                platform.platform_id === "green_mcgill_0"
        );

        expect(remPlatform?.source_feed_id).toBe(
            "rem_20260520"
        );

        expect(metroPlatform?.source_feed_id).toBe(
            "stm_20260805110000_26S"
        );
    });

    it("does not load platforms from other interchanges", () => {
        for (const platform of data.platforms) {
            expect(platform.interchange_id).toBe("mcgill");
        }
    });

    it("adds visualization coordinates to backend platforms", () => {
        const platform = data.platforms.find(
            (item) => item.platform_id === "green_mcgill_0"
        );

        expect(platform?.position).toEqual({
            x: 565,
            y: 450,
        });
    });

    it("rejects a missing platform layout", () => {
        const invalidMock = structuredClone(mock);

        delete invalidMock.platform_layouts["rem_mcgill_0"];

        expect(() =>
            buildStationViewData(mapping, invalidMock)
        ).toThrow("Missing platform layout");
    });

    it("rejects layouts for unknown platforms", () => {
        const invalidMock = structuredClone(mock);

        invalidMock.platform_layouts["fake_platform"] = {
            station_id: "rem_mcgill",
            position: {
                x: 100,
                y: 100,
            },
        };

        expect(() =>
            buildStationViewData(mapping, invalidMock)
        ).toThrow("Unknown platform layout");
    });

    it("rejects duplicate backend platform IDs", () => {
        const invalidMapping = structuredClone(mapping);

        const duplicate = invalidMapping["rem_20260520"].find(
            (platform) => platform.platform_id === "rem_mcgill_0"
        );

        if (!duplicate) {
            throw new Error("Expected McGill REM platform");
        }

        invalidMapping["rem_20260520"].push({
            ...duplicate,
        });

        expect(() =>
            buildStationViewData(invalidMapping, mock)
        ).toThrow("Duplicate platform ID");
    });

it('correctly derives passenger movement start time, end time, path, and status', () => {
        const mockData = structuredClone(mock);
        mockData.passenger_tracks = [
            {
                passenger_id: 'p1',
                group_id: 'g1',
                connection_id: mockData.connections[0]?.id || 'c1',
                samples: [
                    { time_s: 100, position: { x: 0, y: 0 }, phase: 'walking' },
                    { time_s: 150, position: { x: 5, y: 5 }, phase: 'waiting' },
                    { time_s: 200, position: { x: 10, y: 10 }, phase: 'boarded' },
                ],
            },
        ];

        const result = buildStationViewData(mapping, mockData);

        expect(result.passengers).toHaveLength(1);
        expect(result.passengers[0].passenger_id).toBe('p1');
        expect(result.passengers[0].start_time_s).toBe(100);
        expect(result.passengers[0].end_time_s).toBe(200);
        expect(result.passengers[0].path).toEqual([
            { time_s: 100, position: { x: 0, y: 0 } },
            { time_s: 150, position: { x: 5, y: 5 } },
            { time_s: 200, position: { x: 10, y: 10 } },
        ]);
        expect(result.passengers[0].status).toBe('boarded');
    });

    it('rejects unsorted sample tracks with an invalid passenger samples error', () => {
        const mockData = structuredClone(mock);
        mockData.passenger_tracks = [
            {
                passenger_id: 'p2',
                group_id: 'g1',
                connection_id: mockData.connections[0]?.id || 'c1',
                samples: [
                    { time_s: 300, position: { x: 10, y: 10 }, phase: 'missed' },
                    { time_s: 100, position: { x: 0, y: 0 }, phase: 'walking' },
                ],
            },
        ];

        expect(() =>
            buildStationViewData(mapping, mockData)
        ).toThrow("Invalid passenger samples");
    });
});
