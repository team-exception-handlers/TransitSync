// AI contribution: 50% or more AI-generated

// @vitest-environment jsdom

import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { PlaybackTimeline } from "../../src/components/PlaybackTimeline";
import { stationViewData } from "../../src/data/stationViewData";
import { usePlaybackStore } from "../../src/store/usePlaybackStore";

describe("PlaybackTimeline", () => {
    beforeEach(() => {
        usePlaybackStore
            .getState()
            .loadData(stationViewData);
    });

    afterEach(() => {
        cleanup();
    });

    it("renders the simulation start and end times", () => {
        render(<PlaybackTimeline />);

        expect(
            screen.getByText("07:40:00")
        ).toBeDefined();

        expect(
            screen.getByText("07:46:00")
        ).toBeDefined();
    });

    it("renders a timeline slider", () => {
        render(<PlaybackTimeline />);

        const slider = screen.getByRole("slider", {
            name: "Seek simulation time",
        }) as HTMLInputElement;

        expect(slider).toBeDefined();

        expect(slider.min).toBe("0");
        expect(slider.max).toBe("360");
        expect(slider.value).toBe("0");
    });

    it("updates Zustand when the user moves the slider", () => {
        render(<PlaybackTimeline />);

        const slider = screen.getByRole("slider", {
            name: "Seek simulation time",
        });

        fireEvent.change(slider, {
            target: {
                value: "120",
            },
        });

        expect(
            usePlaybackStore.getState().currentTime_s
        ).toBe(120);
    });

    it("updates the displayed time after seeking", () => {
        render(<PlaybackTimeline />);

        const slider = screen.getByRole("slider", {
            name: "Seek simulation time",
        });

        fireEvent.change(slider, {
            target: {
                value: "90",
            },
        });

        expect(
            screen.getByText("07:41:30")
        ).toBeDefined();
    });

    it("supports scrubbing backward", () => {
        render(<PlaybackTimeline />);

        const slider = screen.getByRole("slider", {
            name: "Seek simulation time",
        });

        // seek forward
        fireEvent.change(slider, {
            target: {
                value: "300",
            },
        });

        expect(
            usePlaybackStore.getState().currentTime_s
        ).toBe(300);

        // seek backward
        fireEvent.change(slider, {
            target: {
                value: "60",
            },
        });

        expect(
            usePlaybackStore.getState().currentTime_s
        ).toBe(60);

        expect(
            screen.getByText("07:41:00")
        ).toBeDefined();
    });

    it("does not render play, pause, rewind, or speed buttons", () => {
        render(<PlaybackTimeline />);

        expect(
            screen.queryByRole("button")
        ).toBeNull();
    });
});

describe("PlaybackTimeline mode-switch markers (#60)", () => {
    // The fixture run lasts 360 s and starts at 07:40:00.
    const switchAt = (time_s: number, to_mode: string) => ({
        kind: "mode_switch",
        time_s,
        platform_id: "green_mcgill_0",
        from_mode: to_mode === "headway_regulation" ? "connection_protection" : "headway_regulation",
        to_mode,
    });

    afterEach(() => {
        cleanup();
    });

    it("draws no marker list when the run has no switch entries", () => {
        usePlaybackStore.getState().loadData({ ...stationViewData, decisions: [] });
        render(<PlaybackTimeline />);

        expect(screen.queryByRole("list", { name: "Adaptive mode switches" })).toBeNull();
    });

    it("places each switch at its fraction of the run duration", () => {
        usePlaybackStore.getState().loadData({
            ...stationViewData,
            decisions: [switchAt(90, "headway_regulation"), switchAt(270, "connection_protection")],
        });
        render(<PlaybackTimeline />);

        const markers = screen.getByRole("list", { name: "Adaptive mode switches" })
            .querySelectorAll("li");
        expect(markers).toHaveLength(2);
        // 90 s of 360 s is a quarter of the way along; 270 s is three quarters.
        expect(markers[0].style.left).toBe("25%");
        expect(markers[1].style.left).toBe("75%");
    });

    it("labels each marker with its clock time and both modes", () => {
        usePlaybackStore.getState().loadData({
            ...stationViewData,
            decisions: [switchAt(90, "headway_regulation")],
        });
        render(<PlaybackTimeline />);

        const label = "Mode switch at 07:41:30: connection protection to headway regulation";
        expect(screen.getByText(label)).toBeDefined();
        expect(screen.getByRole("listitem").getAttribute("title")).toBe(label);
    });

    it("ignores hold decisions in the same list", () => {
        const hold = { time_s: 60, train_id: "T1", station_id: "S", platform_id: "P",
            requested_s: 30, applied_s: 30, reason: "hold for transfer group" };
        usePlaybackStore.getState().loadData({
            ...stationViewData,
            decisions: [hold, switchAt(180, "headway_regulation")],
        });
        render(<PlaybackTimeline />);

        const markers = screen.getAllByRole("listitem");
        expect(markers).toHaveLength(1);
        expect(markers[0].style.left).toBe("50%");
    });

    it("keeps the seek slider working with markers present", () => {
        usePlaybackStore.getState().loadData({
            ...stationViewData,
            decisions: [switchAt(90, "headway_regulation")],
        });
        render(<PlaybackTimeline />);
        fireEvent.change(screen.getByRole("slider", { name: "Seek simulation time" }),
            { target: { value: "90" } });

        expect(usePlaybackStore.getState().currentTime_s).toBe(90);
    });
});
