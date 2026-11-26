// AI contribution: 50% or more AI-generated
// @vitest-environment jsdom
/**
 * Run settings panel (#45, #50, #60, #183, #182, #25): controls edit the store, nothing runs
 * until "Run scenario", and a failed run leaves the previous run on screen.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import App from "../../src/App";
import { RunSummary } from "../../src/components/run-summary";
import { RunSettingsPanel } from "../../src/components/run-settings-panel";
import { connectionRuns } from "../../src/data/connection-runs";
import { stationViewData } from "../../src/data/stationViewData";
import { DEFAULT_RUN_SETTINGS } from "../../src/lib/run-settings";
import { runSimulation, type ScenarioRunner } from "../../src/lib/simulation-api";
import { parseStationViewData } from "../../src/lib/validateStationView";
import { usePlaybackStore } from "../../src/store/usePlaybackStore";
import { useRunSettingsStore } from "../../src/store/useRunSettingsStore";
import { useViewStore } from "../../src/store/useViewStore";

const CONNECTION = "mcgill-rem-green";
const draft = () => useRunSettingsStore.getState().draft;
const slider = (name: RegExp) => screen.getByRole("slider", { name }) as HTMLInputElement;
const runButton = () => screen.getByRole("button", { name: "Run scenario" }) as HTMLButtonElement;
// The panel lives on Scenario setup, while the run status and the settings
// summary live on the station view (#408), so App tests move between them.
const openStationView = () => fireEvent.click(screen.getByRole("button", { name: "Station view" }));

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

  it("stores the transfer volume, 60 passengers by default", () => {
    render(<RunSettingsPanel runner={null} />);
    expect(slider(/Transfer volume/).value).toBe("60");

    fireEvent.change(slider(/Transfer volume/), { target: { value: "80" } });

    expect(draft().transfer_volume).toBe(80);
    expect(screen.getByText("80 passengers")).toBeDefined();
  });

  it("stores the disruption preset, none by default", () => {
    render(<RunSettingsPanel runner={null} />);
    const none = screen.getByRole("button", { name: "None" });
    const delay = screen.getByRole("button", { name: "Platform delay" });
    expect(none.getAttribute("aria-pressed")).toBe("true");

    fireEvent.click(delay);

    expect(draft().disruption_enabled).toBe(true);
    expect(draft().disruption_preset).toBe("platform_delay");
    expect(delay.getAttribute("aria-pressed")).toBe("true");
  });

  it("shows CV and start-time controls for uneven headways", () => {
    render(<RunSettingsPanel runner={null} />);
    fireEvent.click(screen.getByRole("button", { name: "Uneven headways" }));

    const irregularity = slider(/Headway irregularity/);
    expect(irregularity.min).toBe("0.05");
    expect(irregularity.max).toBe("1");
    expect(irregularity.step).toBe("0.05");
    expect(irregularity.getAttribute("aria-valuetext")).toBe("0.30 CV");

    fireEvent.change(irregularity, { target: { value: "0.6" } });
    expect(draft().disruption_magnitude).toBe(0.6);
    expect(slider(/Headway irregularity/).getAttribute("aria-valuetext")).toBe("0.60 CV");
  });

  it("uses the shared CV default when an applied run omits its magnitude", () => {
    usePlaybackStore.setState({
      selectedConnectionId: CONNECTION,
      simulatedConnectionIds: [CONNECTION],
    });
    useRunSettingsStore.setState({
      applied: {
        [CONNECTION]: {
          ...DEFAULT_RUN_SETTINGS,
          disruption_preset: "uneven_headways",
          disruption_magnitude: undefined,
        },
      },
    });

    render(<RunSummary />);

    expect(screen.getByText("Headway irregularity")).toBeDefined();
    expect(screen.getByText("0.30 CV")).toBeDefined();
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
    fireEvent.change(slider(/Transfer volume/), { target: { value: "80" } });
    fireEvent.click(screen.getByRole("button", { name: "Platform delay" }));
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
  beforeEach(() => useViewStore.setState({ activeView: "setup" }));
  afterEach(() => useViewStore.setState({ activeView: "station" }));

  it("posts the exact body, loads the run and labels the results with its settings", async () => {
    const fetchImpl = vi.fn(async () => jsonResponse(200, simulatedRun()));
    render(<App runLoader={null} scenarioRunner={runnerWith(fetchImpl)} />);
    fireEvent.click(screen.getByRole("radio", { name: /^Adaptive/ }));
    fireEvent.change(slider(/Maximum hold/), { target: { value: "60" } });
    fireEvent.change(slider(/Error magnitude/), { target: { value: "0" } });
    fireEvent.change(slider(/Transfer volume/), { target: { value: "80" } });
    fireEvent.click(screen.getByRole("button", { name: "Platform delay" }));
    fireEvent.click(runButton());
    await waitFor(() => expect(usePlaybackStore.getState().runStatus).toBe("simulated"));
    openStationView();

    expect(screen.getByRole("status").textContent).toBe("Simulation run · demo scenario output");
    const init = (fetchImpl.mock.calls[0] as unknown as [string, RequestInit])[1];
    expect(JSON.parse(init.body as string)).toStrictEqual({
      connection_id: CONNECTION,
      strategy: "adaptive",
      max_hold_time: 60,
      error_magnitude: 0,
      transfer_volume: 80,
      onboard_load: 300,
      walking_mean_s: 120,
      disruption_enabled: true,
      disruption_preset: "platform_delay",
      disruption_time_s: 120,
      disruption_magnitude: 60,
      irregularity_threshold: 0.25,
    });
    expect(usePlaybackStore.getState().data?.duration_s).toBe(600);
    const summary = screen.getByLabelText("Settings used for this run");
    expect(summary.textContent).toContain("StrategyAdaptive");
    expect(summary.textContent).toContain("Max hold60 s");
    expect(summary.textContent).toContain("Irregularity threshold0.25");
    expect(summary.textContent).toContain("Error magnitude0.0 · upper bound (perfect information)");
    expect(summary.textContent).toContain("Transfer volume80 passengers");
    expect(summary.textContent).toContain("Train frequencyTimetable");
    expect(summary.textContent).toContain("DisruptionPlatform delay");
  });

  it("posts the configured start and CV for uneven headways", async () => {
    const fetchImpl = vi.fn(async () => jsonResponse(200, simulatedRun()));
    render(<App runLoader={null} scenarioRunner={runnerWith(fetchImpl)} />);
    fireEvent.click(screen.getByRole("button", { name: "Uneven headways" }));
    fireEvent.change(slider(/Disruption start/), { target: { value: "300" } });
    fireEvent.change(slider(/Headway irregularity/), { target: { value: "0.55" } });
    fireEvent.click(runButton());
    await waitFor(() => expect(usePlaybackStore.getState().runStatus).toBe("simulated"));

    const init = (fetchImpl.mock.calls[0] as unknown as [string, RequestInit])[1];
    const body = JSON.parse(init.body as string);
    expect(body.disruption_preset).toBe("uneven_headways");
    expect(body.disruption_time_s).toBe(300);
    expect(body.disruption_magnitude).toBe(0.55);
    openStationView();
    const summary = screen.getByLabelText("Settings used for this run");
    expect(summary.textContent).toContain("Disruption start300 s");
    expect(summary.textContent).toContain("Headway irregularity0.55 CV");
  });

  it("shows no settings summary for mock playback", () => {
    render(<App runLoader={null} scenarioRunner={null} />);
    openStationView();

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
    await waitFor(() => expect(usePlaybackStore.getState().runStatus).toBe("error"));
    openStationView();

    expect(screen.getByRole("status").textContent)
      .toBe("Run failed · showing the previous simulation run");
    expect(usePlaybackStore.getState().data?.duration_s).toBe(600);
    // The label still describes the run on screen, not the failed attempt.
    expect(screen.getByLabelText("Settings used for this run").textContent).toContain("Max hold300 s");
  });
});
