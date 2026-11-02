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
});