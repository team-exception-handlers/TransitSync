// AI contribution: 50% or more AI-generated
// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import App from "../../src/App";
import { stationViewData } from "../../src/data/stationViewData";
import { parseStationViewData } from "../../src/lib/validateStationView";
import { usePlaybackStore } from "../../src/store/usePlaybackStore";
import type { StationViewData } from "../../src/types/stationView";

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

    it("stays on the mock run and labels it when no API is configured", () => {
        render(<App runLoader={null} />);

        expect(screen.getByRole("status").textContent).toContain("Mock playback");
    });
});

describe("Selected connection to simulation run (#79)", () => {
    beforeEach(() => {
        vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(null);
        usePlaybackStore.setState({
            data: null,
            currentTime_s: 0,
            selectedConnectionId: null,
            availableRuns: [],
            simulatedConnectionIds: [],
            runStatus: "mock",
            runError: null,
        });
    });

    afterEach(() => {
        cleanup();
        vi.restoreAllMocks();
    });

    it("loads the selected connection's run and shows it as simulator output", async () => {
        const run = structuredClone(stationViewData);
        run.duration_s = 600;
        const loader = vi.fn(async () => parseStationViewData(run));
        render(<App runLoader={loader} />);

        await waitFor(() => expect(screen.getByRole("status").textContent)
            .toBe("Simulation run · demo scenario output"));
        expect(loader).toHaveBeenCalledWith("mcgill-rem-green", expect.any(AbortSignal));
        expect(usePlaybackStore.getState().data?.duration_s).toBe(600);
    });

    it("requests the new connection and aborts the old request on a switch", async () => {
        const signals: AbortSignal[] = [];
        const loader = vi.fn((_id: string, signal?: AbortSignal) => {
            if (signal) signals.push(signal);
            return new Promise<StationViewData>(() => {});
        });
        render(<App runLoader={loader} />);
        await waitFor(() => expect(loader).toHaveBeenCalledTimes(1));

        fireEvent.click(screen.getByRole("button", { name: /Gare Centrale/ }));

        await waitFor(() => expect(loader).toHaveBeenCalledTimes(2));
        expect(loader.mock.calls[1][0]).toBe("gare_centrale_bonaventure-rem-orange");
        expect(signals[0].aborted).toBe(true);
        expect(signals[1].aborted).toBe(false);
        expect(screen.getByRole("status").textContent).toBe("Loading simulation run…");
    });

    it("keeps the mock run on screen and says the run is unavailable when loading fails", async () => {
        const loader = vi.fn(async () => {
            throw new Error("Simulation run failed");
        });
        render(<App runLoader={loader} />);

        await waitFor(() => expect(screen.getByRole("status").textContent)
            .toBe("Showing mock playback · simulation run unavailable"));
        expect(screen.getByRole("status").getAttribute("title")).toBe("Simulation run failed");
        expect(usePlaybackStore.getState().data?.interchange.id).toBe("mcgill");
    });
});

