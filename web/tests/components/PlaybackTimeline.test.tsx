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