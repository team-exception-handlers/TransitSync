// AI contribution: 50% or more AI-generated
// @vitest-environment jsdom
/**
 * Run settings panel (#45, #50, #60, #183, #182, #25): controls edit the store, nothing runs
 * until "Run scenario", and a failed run leaves the previous run on screen.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import App from "../../src/App";
import { RunSettingsPanel } from "../../src/components/run-settings-panel";
import { connectionRuns } from "../../src/data/connection-runs";
import { stationViewData } from "../../src/data/stationViewData";
import { DEFAULT_RUN_SETTINGS } from "../../src/lib/run-settings";
import { runSimulation, type ScenarioRunner } from "../../src/lib/simulation-api";
import { parseStationViewData } from "../../src/lib/validateStationView";
import { usePlaybackStore } from "../../src/store/usePlaybackStore";
import { useRunSettingsStore } from "../../src/store/useRunSettingsStore";

const CONNECTION = "mcgill-rem-green";
const draft = () => useRunSettingsStore.getState().draft;
const slider = (name: RegExp) => screen.getByRole("slider", { name }) as HTMLInputElement;
const runButton = () => screen.getByRole("button", { name: "Run scenario" }) as HTMLButtonElement;

/** A valid run that differs from the fixture, so a successful load is visible. */
function simulatedRun() {
  const run = structuredClone(stationViewData);
  run.duration_s = 600;
  return run;
}

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

/** Runner backed by the real client and a fake fetch: no network is used. */
function runnerWith(fetchImpl: typeof fetch): ScenarioRunner {
  return (connectionId, settings, signal) =>
    runSimulation(connectionId, settings, { baseUrl: "http://api.test", fetchImpl, signal });
}

beforeEach(() => {
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(null);
  useRunSettingsStore.setState({ draft: DEFAULT_RUN_SETTINGS, applied: {} });
  usePlaybackStore.setState({ simulatedConnectionIds: [], runStatus: "mock", runError: null });
  usePlaybackStore.getState().setAvailableRuns(connectionRuns);
  usePlaybackStore.getState().loadData(stationViewData);
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("run settings controls", () => {
  it("offers one radio card per strategy with No control selected", () => {
    render(<RunSettingsPanel runner={null} />);

    expect(screen.getAllByRole("radio")).toHaveLength(6);
    expect((screen.getByRole("radio", { name: /^No control/ }) as HTMLInputElement).checked).toBe(true);
    expect(screen.getByText("Hold to keep even gaps between trains.")).toBeDefined();
  });

  it("stores the selected strategy and shows it as checked", () => {
    render(<RunSettingsPanel runner={null} />);
    fireEvent.click(screen.getByRole("radio", { name: /^Coordinated/ }));

    expect(draft().strategy).toBe("rolling_horizon");
    expect((screen.getByRole("radio", { name: /^Coordinated/ }) as HTMLInputElement).checked).toBe(true);
  });

  it("stores the maximum hold and shows it in seconds", () => {
    render(<RunSettingsPanel runner={null} />);
    fireEvent.change(slider(/Maximum hold/), { target: { value: "45" } });

    expect(draft().max_hold_time).toBe(45);
    expect(screen.getByText("45 s")).toBeDefined();
    expect(slider(/Maximum hold/).getAttribute("aria-valuetext")).toBe("45 s");
  });

  it("limits the maximum hold slider to 5-300 s in steps of 5", () => {
    render(<RunSettingsPanel runner={null} />);
    const input = slider(/Maximum hold/);

    expect(input.min).toBe("5");
    expect(input.max).toBe("300");
    expect(input.step).toBe("5");
  });

  it("enables the irregularity threshold only for Adaptive", () => {
    render(<RunSettingsPanel runner={null} />);
    expect(slider(/Irregularity threshold/).disabled).toBe(true);

    fireEvent.click(screen.getByRole("radio", { name: /^Adaptive/ }));
    expect(slider(/Irregularity threshold/).disabled).toBe(false);

    fireEvent.change(slider(/Irregularity threshold/), { target: { value: "0.4" } });
    expect(draft().irregularity_threshold).toBe(0.4);
    expect(screen.getByText("0.40")).toBeDefined();
  });

  it("stores the error magnitude and labels zero as the upper bound", () => {
    render(<RunSettingsPanel runner={null} />);
    expect(screen.getByText("1.0")).toBeDefined();

    fireEvent.change(slider(/Error magnitude/), { target: { value: "2.5" } });
    expect(draft().error_magnitude).toBe(2.5);
    expect(screen.getByText("2.5")).toBeDefined();

    fireEvent.change(slider(/Error magnitude/), { target: { value: "0" } });
    expect(draft().error_magnitude).toBe(0);
    expect(screen.getByText("0.0 · upper bound (perfect information)")).toBeDefined();
  });

  it("limits the error magnitude slider to 0-3", () => {
    render(<RunSettingsPanel runner={null} />);

    expect(slider(/Error magnitude/).min).toBe("0");
    expect(slider(/Error magnitude/).max).toBe("3");
  });

  it("stores the passenger flow, with Normal pressed by default", () => {
    render(<RunSettingsPanel runner={null} />);
    const flow = screen.getByRole("group", { name: "Passenger flow" });
    const pressed = () => Array.from(flow.querySelectorAll("button"))
      .filter((button) => button.getAttribute("aria-pressed") === "true")
      .map((button) => button.textContent);
    expect(pressed()).toStrictEqual(["Normal"]);

    fireEvent.click(screen.getByRole("button", { name: "High" }));

    expect(draft().passenger_flow).toBe("High");
    expect(pressed()).toStrictEqual(["High"]);
  });

  it("stores the disruption switch, off by default", () => {
    render(<RunSettingsPanel runner={null} />);
    const on = screen.getByRole("button", { name: "On" });
    expect(on.getAttribute("aria-pressed")).toBe("false");

    fireEvent.click(on);

    expect(draft().disruption_enabled).toBe(true);
    expect(on.getAttribute("aria-pressed")).toBe("true");
    expect(screen.getByRole("button", { name: "Off" }).getAttribute("aria-pressed")).toBe("false");
  });

  it("opens and closes the maximum hold help note", () => {
    render(<RunSettingsPanel runner={null} />);
    const help = screen.getByRole("button", { name: "What is maximum hold?" });
    const note = screen.getByText(/The longest any train may wait for transfers/);

    expect(help.getAttribute("aria-expanded")).toBe("false");
    expect(note.hidden).toBe(true);
    fireEvent.click(help);
    expect(help.getAttribute("aria-expanded")).toBe("true");
    expect(note.hidden).toBe(false);
  });

  it("restores the backend defaults with Reset to defaults", () => {
    render(<RunSettingsPanel runner={null} />);
    fireEvent.click(screen.getByRole("radio", { name: /^Adaptive/ }));
    fireEvent.change(slider(/Maximum hold/), { target: { value: "60" } });
    fireEvent.change(slider(/Error magnitude/), { target: { value: "0" } });
    fireEvent.click(screen.getByRole("button", { name: "High" }));
    fireEvent.click(screen.getByRole("button", { name: "On" }));
    fireEvent.click(screen.getByRole("button", { name: "Reset to defaults" }));

    expect(draft()).toStrictEqual(DEFAULT_RUN_SETTINGS);
    expect(screen.getByText("300 s")).toBeDefined();
    expect(slider(/Irregularity threshold/).disabled).toBe(true);
  });

  it("disables Run scenario and says why when no API is configured", () => {
    render(<RunSettingsPanel runner={null} />);

    expect(runButton().disabled).toBe(true);
    expect(screen.getByText(/No simulation API is configured/)).toBeDefined();
  });
});

describe("Run scenario", () => {
  it("runs only on the button, with the settings shown at that moment", async () => {
    const runner = vi.fn<ScenarioRunner>(async () => parseStationViewData(simulatedRun()));
    render(<RunSettingsPanel runner={runner} />);
    fireEvent.click(screen.getByRole("radio", { name: /^Connection protection/ }));
    fireEvent.change(slider(/Maximum hold/), { target: { value: "45" } });
    expect(runner).not.toHaveBeenCalled();

    fireEvent.click(runButton());

    await waitFor(() => expect(usePlaybackStore.getState().runStatus).toBe("simulated"));
    expect(runner).toHaveBeenCalledTimes(1);
    expect(runner.mock.calls[0][0]).toBe(CONNECTION);
    expect(runner.mock.calls[0][1]).toStrictEqual({ ...DEFAULT_RUN_SETTINGS,
      strategy: "connection_protection", max_hold_time: 45 });
    expect(usePlaybackStore.getState().data?.duration_s).toBe(600);
    expect(useRunSettingsStore.getState().applied[CONNECTION].max_hold_time).toBe(45);
  });

  it("shows a running state and blocks a second run while one is in flight", async () => {
    const runner = vi.fn<ScenarioRunner>(() => new Promise(() => {}));
    render(<RunSettingsPanel runner={runner} />);
    fireEvent.click(runButton());

    const running = await screen.findByRole("button", { name: "Running…" });
    expect((running as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(running);
    expect(runner).toHaveBeenCalledTimes(1);
  });

  it("cancels the run when the user switches connection", async () => {
    const signals: AbortSignal[] = [];
    const runner = vi.fn<ScenarioRunner>((_id, _settings, signal) => {
      if (signal) signals.push(signal);
      return new Promise(() => {});
    });
    render(<RunSettingsPanel runner={runner} />);
    fireEvent.click(runButton());
    await waitFor(() => expect(signals).toHaveLength(1));

    usePlaybackStore.getState().selectConnection("edouard_montpetit-rem-blue");

    await waitFor(() => expect(signals[0].aborted).toBe(true));
  });
});

describe("Run scenario through the API client", () => {
  it("posts the exact body, loads the run and labels the results with its settings", async () => {
    const fetchImpl = vi.fn(async () => jsonResponse(200, simulatedRun()));
    render(<App runLoader={null} scenarioRunner={runnerWith(fetchImpl)} />);
    fireEvent.click(screen.getByRole("radio", { name: /^Adaptive/ }));
    fireEvent.change(slider(/Maximum hold/), { target: { value: "60" } });
    fireEvent.change(slider(/Error magnitude/), { target: { value: "0" } });
    fireEvent.click(screen.getByRole("button", { name: "High" }));
    fireEvent.click(screen.getByRole("button", { name: "On" }));
    fireEvent.click(runButton());

    await waitFor(() => expect(screen.getByRole("status").textContent)
      .toBe("Simulation run · demo scenario output"));
    const init = (fetchImpl.mock.calls[0] as unknown as [string, RequestInit])[1];
    expect(JSON.parse(init.body as string)).toStrictEqual({
      connection_id: CONNECTION,
      strategy: "adaptive",
      max_hold_time: 60,
      error_magnitude: 0,
      passenger_flow: "High",
      disruption_enabled: true,
      irregularity_threshold: 0.25,
    });
    expect(usePlaybackStore.getState().data?.duration_s).toBe(600);
    const summary = screen.getByLabelText("Settings used for this run");
    expect(summary.textContent).toContain("StrategyAdaptive");
    expect(summary.textContent).toContain("Max hold60 s");
    expect(summary.textContent).toContain("Irregularity threshold0.25");
    expect(summary.textContent).toContain("Error magnitude0.0 · upper bound (perfect information)");
    expect(summary.textContent).toContain("Passenger flowHigh");
    expect(summary.textContent).toContain("DisruptionOn");
  });

  it("shows no settings summary for mock playback", () => {
    render(<App runLoader={null} scenarioRunner={null} />);

    expect(screen.queryByLabelText("Settings used for this run")).toBeNull();
  });

  it.each([
    ["an unknown connection (404)", () => jsonResponse(404, { detail: "Unknown connection: x" }),
      "The simulator does not have this connection. Choose another connection and run again."],
    ["rejected settings (422)",
      () => jsonResponse(422, { detail: [{ loc: ["body", "max_hold_time"], msg: "Input should be a multiple of 5" }] }),
      "The simulator rejected these settings (max_hold_time: Input should be a multiple of 5)."],
  ])("explains %s and keeps the previous run", async (_case, respond, message) => {
    const before = usePlaybackStore.getState().data;
    render(<App runLoader={null} scenarioRunner={runnerWith(vi.fn(async () => respond()))} />);
    fireEvent.click(runButton());

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toBe(message);
    expect(usePlaybackStore.getState().data).toBe(before);
    expect(runButton().disabled).toBe(false);
  });

  it("explains a network failure and keeps the previous run", async () => {
    const before = usePlaybackStore.getState().data;
    const fetchImpl = vi.fn(async () => {
      throw new TypeError("Failed to fetch");
    });
    render(<App runLoader={null} scenarioRunner={runnerWith(fetchImpl)} />);
    fireEvent.click(runButton());

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toBe(
      "Could not reach the simulation API at http://api.test. Check that the backend is running.");
    expect(usePlaybackStore.getState().data).toBe(before);
  });

  it("keeps an earlier simulation run, and says so, when a re-run fails", async () => {
    const fetchImpl = vi.fn()
      .mockResolvedValueOnce(jsonResponse(200, simulatedRun()))
      .mockResolvedValueOnce(jsonResponse(500, { detail: "Simulation run failed" }));
    render(<App runLoader={null} scenarioRunner={runnerWith(fetchImpl)} />);
    fireEvent.click(runButton());
    await waitFor(() => expect(usePlaybackStore.getState().runStatus).toBe("simulated"));

    fireEvent.change(slider(/Maximum hold/), { target: { value: "30" } });
    fireEvent.click(runButton());

    await waitFor(() => expect(screen.getByRole("status").textContent)
      .toBe("Run failed · showing the previous simulation run"));
    expect(usePlaybackStore.getState().data?.duration_s).toBe(600);
    // The label still describes the run on screen, not the failed attempt.
    expect(screen.getByLabelText("Settings used for this run").textContent).toContain("Max hold300 s");
  });
});
