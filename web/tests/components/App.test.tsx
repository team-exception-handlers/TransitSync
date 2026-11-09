// AI contribution: 50% or more AI-generated
// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import App from "../../src/App";
import { stationViewData } from "../../src/data/stationViewData";
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

    it("updates the heading when selecting a second connection within the same run", () => {
        const run = structuredClone(stationViewData);
        const first = run.connections[0];
        const second = { ...first, id: "second-connection", label: "Second connection" };
        run.connections.push(second);
        usePlaybackStore.getState().setAvailableRuns([run]);
        usePlaybackStore.getState().loadData(run);
        render(<App />);

        expect(screen.getByRole("heading", { level: 1 }).textContent).toBe(first.label);
        fireEvent.click(screen.getByRole("button", { name: /Second connection/ }));

        expect(usePlaybackStore.getState().data).toStrictEqual(run);
        expect(usePlaybackStore.getState().selectedConnectionId).toBe(second.id);
        expect(screen.getByRole("heading", { level: 1 }).textContent).toBe(second.label);

        fireEvent.change(screen.getByRole("slider", { name: "Seek simulation time" }),
            { target: { value: "60" } });
        expect(screen.getByRole("heading", { level: 1 }).textContent).toBe(second.label);
        fireEvent.click(screen.getByRole("button", { name: new RegExp(first.label) }));
        expect(screen.getByRole("heading", { level: 1 }).textContent).toBe(first.label);
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
