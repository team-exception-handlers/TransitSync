// AI contribution: 50% or more AI-generated
import { describe, expect, it } from "vitest";
import { stationViewData } from "../../src/data/stationViewData";
import { getNetworkSnapshot } from "../../src/lib/getNetworkSnapshot";

const data = stationViewData;

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