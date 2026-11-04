// AI contribution: 50% or more AI-generated
// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import App from "../../src/App";
import { connectionRuns } from "../../src/data/connection-runs";
import { usePlaybackStore } from "../../src/store/usePlaybackStore";

describe("TransitSync application shell", () => {
    beforeEach(() => {
        vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(null);
        // reset the shared state before rendering the app
        usePlaybackStore.setState({
            data: null,
            currentTime_s: 0,
            selectedConnectionId: null,
            availableRuns: [],
        });
    });

    afterEach(() => {
        cleanup();
        vi.restoreAllMocks();
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

    it("renders the required Canvas station-view consumer", () => {
        render(<App />);

        const stationRegion = screen.getByRole("region", {
            name: "Station view",
        });

        expect(stationRegion.querySelector("canvas")?.width).toBe(800);
        expect(screen.getByRole("img").getAttribute("aria-label")).toContain("McGill");
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

    it("indicates the active shared connection", () => {
        render(<App />);

        expect(
            screen.getByRole("button", { name: /McGill/ }).getAttribute("aria-pressed")
        ).toBe("true");
    });

    it("shows the selected connection's label in the heading, not connections[0]", () => {
        usePlaybackStore.getState().setAvailableRuns(connectionRuns);
        render(<App />);

        const buttons = screen.getAllByRole("button", { name: /line$/ });
        fireEvent.click(buttons[buttons.length - 1]);

        const selectedId = usePlaybackStore.getState().selectedConnectionId;
        const selectedLabel = usePlaybackStore.getState().data?.connections
            .find((connection) => connection.id === selectedId)?.label;

        expect(selectedLabel).toBeTruthy();
        expect(screen.getByRole("heading", { level: 1 }).textContent).toBe(selectedLabel);
    });

    it("keeps the heading on the selected connection through a playback time change", () => {
        render(<App />);

        const buttons = screen.getAllByRole("button", { name: /line$/ });
        fireEvent.click(buttons[buttons.length - 1]);
        const selectedLabel = screen.getByRole("heading", { level: 1 }).textContent;

        fireEvent.change(
            screen.getByRole("slider", { name: "Seek simulation time" }),
            { target: { value: "60" } },
        );

        expect(screen.getByRole("heading", { level: 1 }).textContent).toBe(selectedLabel);
    });
});
