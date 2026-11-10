// AI contribution: 50% or more AI-generated
import { describe, expect, it, vi } from "vitest";
import { stationViewData } from "../../src/data/stationViewData";
import { getNetworkSnapshot } from "../../src/lib/getNetworkSnapshot";
import type { StationViewData } from "../../src/types/stationView";

const data = stationViewData;

/**
 * A minimal fixture isolating a single passenger walking around an L-shaped
 * corridor bend, so a chord shortcut is easy to tell apart from arc-length
 * travel along the actual path.
 */
function buildBendFixture(): StationViewData {
    return {
        schema_version: 1,
        interchange: { id: "fixture", name: "Fixture Interchange" },
        start_clock_s: 0,
        duration_s: 100,
        map: { width: 100, height: 100 },
        stations: [
            { id: "station-a", name: "A", line_id: "green", position: { x: 0, y: 0 } },
            { id: "station-b", name: "B", line_id: "blue", position: { x: 10, y: 10 } },
        ],
        platforms: [
            {
                platform_id: "platform-a",
                interchange_id: "fixture",
                line_id: "green",
                direction_id: 0,
                direction_label: "A",
                stop_id: "stop-a",
                stop_name: "A",
                route_ids: [],
                station_id: "station-a",
                source_feed_id: "fixture",
                position: { x: 0, y: 0 },
                color: "#000000",
            },
            {
                platform_id: "platform-b",
                interchange_id: "fixture",
                line_id: "blue",
                direction_id: 0,
                direction_label: "B",
                stop_id: "stop-b",
                stop_name: "B",
                route_ids: [],
                station_id: "station-b",
                source_feed_id: "fixture",
                position: { x: 10, y: 10 },
                color: "#000000",
            },
        ],
        corridors: [
            {
                id: "corridor-bend",
                label: "Bend corridor",
                from_platform_id: "platform-a",
                to_platform_id: "platform-b",
                // An L-shaped path: right along x, then down along y.
                path: [
                    { x: 0, y: 0 },
                    { x: 10, y: 0 },
                    { x: 10, y: 10 },
                ],
            },
        ],
        connections: [
            {
                id: "connection-bend",
                label: "A to B",
                from_platform_id: "platform-a",
                to_platform_id: "platform-b",
                corridor_id: "corridor-bend",
            },
        ],
        passenger_tracks: [
            {
                passenger_id: "bend-passenger",
                group_id: "bend-group",
                connection_id: "connection-bend",
                samples: [
                    { time_s: 0, position: { x: 0, y: 0 }, phase: "walking" },
                    { time_s: 20, position: { x: 10, y: 10 }, phase: "walking" },
                ],
            },
        ],
        train_events: [],
        passengers: [],
    };
}

describe("getNetworkSnapshot corridor following", () => {
    it("reuses fixed corridor geometry across frames and prepares a new run separately", () => {
        const fixture = buildBendFixture();
        const hypot = vi.spyOn(Math, "hypot");
        try {
            const original = getNetworkSnapshot(fixture, 5);
            expect(hypot).toHaveBeenCalled();
            hypot.mockClear();
            expect(getNetworkSnapshot(fixture, 15).passengers[0].position).toEqual({ x: 10, y: 5 });
            expect(getNetworkSnapshot(fixture, 5)).toEqual(original);
            expect(hypot).not.toHaveBeenCalled();

            const reverse = buildBendFixture();
            reverse.passenger_tracks[0].samples[0].position = { x: 10, y: 10 };
            reverse.passenger_tracks[0].samples[1].position = { x: 0, y: 0 };
            expect(getNetworkSnapshot(reverse, 5).passengers[0].position).toEqual({ x: 10, y: 5 });
            expect(hypot).toHaveBeenCalled();
        } finally {
            hypot.mockRestore();
        }
    });

    it("interpolates along the corridor polyline rather than a straight chord across a bend", () => {
        const fixture = buildBendFixture();

        // Halfway through the sample interval, by arc length, the passenger
        // should be exactly at the corner of the L-shaped corridor.
        const snapshot = getNetworkSnapshot(fixture, 10);
        const passenger = snapshot.passengers.find(
            (item) => item.passenger_id === "bend-passenger"
        );

        expect(passenger).toBeDefined();
        expect(passenger?.position).toEqual({ x: 10, y: 0 });

        // A straight chord between (0,0) and (10,10) would have placed the
        // passenger at (5,5), cutting across the corner.
        expect(passenger?.position).not.toEqual({ x: 5, y: 5 });
    });

    it("interpolates proportionally to arc length on the first leg of the bend", () => {
        const fixture = buildBendFixture();

        // Total arc length is 20; at t=5 (quarter of the 20s interval), the
        // passenger is a quarter of the way along, still on the first leg.
        const snapshot = getNetworkSnapshot(fixture, 5);
        const passenger = snapshot.passengers.find(
            (item) => item.passenger_id === "bend-passenger"
        );

        expect(passenger?.position).toEqual({ x: 5, y: 0 });
    });
});

describe("getNetworkSnapshot", () => {
    it("returns the requested simulation timestamp", () => {
        const snapshot = getNetworkSnapshot(data, 150);

        expect(snapshot.time_s).toBe(150);
    });

    it("returns no passengers before they enter the interchange", () => {
        const snapshot = getNetworkSnapshot(data, 0);

        expect(snapshot.passengers).toHaveLength(0);
    });

    it("returns passenger positions after arrival", () => {
        const snapshot = getNetworkSnapshot(data, 90);

        expect(snapshot.passengers.length).toBeGreaterThan(0);

        const passenger = snapshot.passengers.find(
            (item) => item.passenger_id === "p-001"
        );

        expect(passenger).toBeDefined();
    });

    it("interpolates walking positions correctly", () => {
        const snapshot = getNetworkSnapshot(data, 85);

        const passenger = snapshot.passengers.find(
            (item) => item.passenger_id === "p-001"
        );

        expect(passenger).toBeDefined();

        expect(passenger?.position.x).toBeCloseTo(389);
        expect(passenger?.position.y).toBeCloseTo(135);
    });

    it("keeps queued passengers stationary", () => {
        const snapshot = getNetworkSnapshot(data, 138);

        const passenger = snapshot.passengers.find(
            (item) => item.passenger_id === "p-002"
        );

        expect(passenger?.phase).toBe("queued");

        expect(passenger?.position).toEqual({
            x: 405,
            y: 310,
        });
    });

    it("removes boarded passengers from station snapshots", () => {
        const beforeBoarding = getNetworkSnapshot(data, 169);

        const afterBoarding = getNetworkSnapshot(data, 170);

        expect(
            beforeBoarding.passengers.some(
                (passenger) => passenger.passenger_id === "p-001"
            )
        ).toBe(true);

        expect(
            afterBoarding.passengers.some(
                (passenger) => passenger.passenger_id === "p-001"
            )
        ).toBe(false);
    });

    it("shows a train after it arrives", () => {
        const snapshot = getNetworkSnapshot(data, 150);

        const train = snapshot.trains_at_platforms.find(
            (item) => item.train_id === "metro-001"
        );

        expect(train).toBeDefined();

        expect(train?.platform_id).toBe("green_mcgill_0");
    });

    it("removes a train after it departs", () => {
        const snapshot = getNetworkSnapshot(data, 175);

        const train = snapshot.trains_at_platforms.find(
            (item) => item.train_id === "metro-001"
        );

        expect(train).toBeUndefined();
    });

    it("returns identical snapshots after seeking backward", () => {
        const original = getNetworkSnapshot(data, 100);

        getNetworkSnapshot(data, 300);

        const restored = getNetworkSnapshot(data, 100);

        expect(restored).toEqual(original);
    });

    it("does not mutate the original simulation data", () => {
        const originalTracks = structuredClone(
            data.passenger_tracks
        );

        const originalEvents = structuredClone(
            data.train_events
        );

        getNetworkSnapshot(data, 200);

        expect(data.passenger_tracks).toEqual(originalTracks);
        expect(data.train_events).toEqual(originalEvents);
    });

    it("clamps negative timestamps", () => {
        const snapshot = getNetworkSnapshot(data, -50);

        expect(snapshot.time_s).toBe(0);
    });

    it("clamps timestamps beyond the simulation duration", () => {
        const snapshot = getNetworkSnapshot(data, 9999);

        expect(snapshot.time_s).toBe(data.duration_s);
    });
});
