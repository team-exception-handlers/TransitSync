// AI contribution: 50% or more AI-generated
// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import App from "../../src/App";
import { usePlaybackStore } from "../../src/store/usePlaybackStore";

describe("TransitSync application shell", () => {
    beforeEach(() => {
        // reset the shared state before rendering the app
        usePlaybackStore.setState({
            data: null,
            currentTime_s: 0,
            selectedConnectionId: null,
        });
    });

    afterEach(() => {
        cleanup();
    });

    it("renders the TransitSync branding", () => {
        render(<App />);

        expect(
            screen.getByText("TransitSync")
        ).toBeDefined();
    });

    it("renders the Workspace sidebar", () => {
        render(<App />);

        expect(
            screen.getByText("Workspace")
        ).toBeDefined();

        expect(
            screen.getByText("Station view")
        ).toBeDefined();
    });

    it("loads the mock interchange data", () => {
        render(<App />);

        const state = usePlaybackStore.getState();

        expect(state.data).not.toBeNull();

        expect(state.data?.interchange.id).toBe(
            "mcgill"
        );
    });

    it("renders an empty station-view region", () => {
        render(<App />);

        const stationRegion = screen.getByRole("region", {
            name: "Station view",
        });

        expect(stationRegion.childElementCount).toBe(0);
    });

    it("renders the simulation clock", () => {
        render(<App />);

        expect(
            screen.getByText("Simulation clock")
        ).toBeDefined();

        expect(
            screen.getAllByText("07:40:00").length
        ).toBeGreaterThan(0);
    });

    it("updates the clock when seeking", () => {
        render(<App />);

        const slider = screen.getByRole("slider", {
            name: "Seek simulation time",
        });

        fireEvent.change(slider, {
            target: {
                value: "120",
            },
        });

        expect(
            screen.getAllByText("07:42:00").length
        ).toBeGreaterThan(0);
    });

    it("does not include controls assigned to Person 8", () => {
        render(<App />);

        expect(
            screen.queryByRole("button")
        ).toBeNull();
    });
});