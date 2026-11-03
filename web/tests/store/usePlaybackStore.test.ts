// AI contribution: 50% or more AI-generated
import {beforeEach, describe, expect, it } from "vitest";
import { stationViewData } from "../../src/data/stationViewData";
import { usePlaybackStore } from "../../src/store/usePlaybackStore";

describe("usePlaybackStore", () => {
    beforeEach(() => {
        usePlaybackStore
            .getState()
            .loadData(stationViewData);
    });

    it("loads the McGill mock data", () => {
        const state = usePlaybackStore.getState();

        expect(state.data?.interchange.id).toBe("mcgill");

        expect(state.data?.platforms).toHaveLength(4);
    });

    it("starts at the beginning of the simulation", () => {
        const state = usePlaybackStore.getState();

        expect(state.currentTime_s).toBe(0);
    });

    it("tracks the current playback position", () => {
        usePlaybackStore.getState().seek(120);

        expect(
            usePlaybackStore.getState().currentTime_s
        ).toBe(120);
    });

    it("supports seeking forward", () => {
        usePlaybackStore.getState().seek(100);
        usePlaybackStore.getState().seek(250);

        expect(
            usePlaybackStore.getState().currentTime_s
        ).toBe(250);
    });

    it("supports seeking backward", () => {
        usePlaybackStore.getState().seek(250);
        usePlaybackStore.getState().seek(100);

        expect(
            usePlaybackStore.getState().currentTime_s
        ).toBe(100);
    });

    it("prevents seeking before the run starts", () => {
        usePlaybackStore.getState().seek(-100);

        expect(
            usePlaybackStore.getState().currentTime_s
        ).toBe(0);
    });

    it("prevents seeking beyond the end of the run", () => {
        usePlaybackStore.getState().seek(9999);

        expect(
            usePlaybackStore.getState().currentTime_s
        ).toBe(stationViewData.duration_s);
    });

    it("reconstructs network state at the current position", () => {
        usePlaybackStore.getState().seek(150);

        const snapshot = usePlaybackStore
            .getState()
            .snapshot();

        expect(snapshot?.time_s).toBe(150);

        expect(
            snapshot?.trains_at_platforms.some(
                (train) => train.train_id === "metro-001"
            )
        ).toBe(true);
    });

    it("returns network state at an arbitrary time", () => {
        const snapshot = usePlaybackStore
            .getState()
            .getSnapshotAt(100);

        expect(snapshot?.time_s).toBe(100);
    });

    it("does not move the timeline when querying another time", () => {
        usePlaybackStore.getState().seek(200);

        usePlaybackStore.getState().getSnapshotAt(50);

        expect(
            usePlaybackStore.getState().currentTime_s
        ).toBe(200);
    });

    it("restores the same state after seeking backward", () => {
        usePlaybackStore.getState().seek(100);

        const original = usePlaybackStore
            .getState()
            .snapshot();

        usePlaybackStore.getState().seek(300);
        usePlaybackStore.getState().seek(100);

        const restored = usePlaybackStore
            .getState()
            .snapshot();

        expect(restored).toEqual(original);
    });

    it("initializes the selected connection", () => {
        expect(
            usePlaybackStore.getState().selectedConnectionId
        ).toBe("mcgill-rem-green");
    });

    it("rejects unknown connections", () => {
        expect(() => {
            usePlaybackStore
                .getState()
                .selectConnection("unknown");
        }).toThrow("Unknown connection");
    });

    it("loads a run paused at its initial position", () => {
        const state = usePlaybackStore.getState();

        expect(state.isPlaying).toBe(false);
        expect(state.updatedAt_ms).toBeNull();
    });
});
