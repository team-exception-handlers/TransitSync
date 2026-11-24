// AI contribution: 50% or more AI-generated
// @vitest-environment jsdom
/**
 * Time-of-day preset picker on Scenario setup (#260 to #263): it lists the
 * API's presets, fills every control with the selected one, shows its
 * conditions, and the run request carries the preset and its values.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import App from "../../src/App";
import { PresetPicker } from "../../src/components/preset-picker";
import { RunSettingsPanel } from "../../src/components/run-settings-panel";
import { connectionRuns } from "../../src/data/connection-runs";
import { stationViewData } from "../../src/data/stationViewData";
import { DEFAULT_RUN_SETTINGS } from "../../src/lib/run-settings";
import type { ScenarioRunner } from "../../src/lib/simulation-api";
import { parseStationViewData } from "../../src/lib/validateStationView";
import { usePlaybackStore } from "../../src/store/usePlaybackStore";
import { useRunSettingsStore } from "../../src/store/useRunSettingsStore";
import { useViewStore } from "../../src/store/useViewStore";
import type { ScenarioPreset } from "../../src/types/runSettings";
import { MORNING, SUNDAY } from "../lib/preset-fixtures";

const draft = () => useRunSettingsStore.getState().draft;
const slider = (name: RegExp) => screen.getByRole("slider", { name }) as HTMLInputElement;
const runButton = () => screen.getByRole("button", { name: "Run scenario" }) as HTMLButtonElement;
const runner: ScenarioRunner = vi.fn(async () => parseStationViewData(stationViewData));

/** The picker above the panel, as Scenario setup lays them out. */
function Setup({ presets }: Readonly<{ presets: readonly ScenarioPreset[] }>) {
  return (
    <>
      <PresetPicker presets={presets} />
      <RunSettingsPanel runner={runner} />
    </>
  );
}

beforeEach(() => {
  useRunSettingsStore.setState({ draft: DEFAULT_RUN_SETTINGS, applied: {} });
  usePlaybackStore.getState().setAvailableRuns(connectionRuns);
  usePlaybackStore.getState().selectConnection("mcgill-rem-green");
});
afterEach(cleanup);

describe("preset picker", () => {
  it("is hidden when the API listed no presets", () => {
    render(<Setup presets={[]} />);
    expect(screen.queryByRole("group", { name: "Time of day" })).toBeNull();
  });

  it("fills every control with the selected preset and lists its conditions", () => {
    render(<Setup presets={[MORNING, SUNDAY]} />);
    expect(screen.getByRole("radio", { name: /^Custom/ })).toHaveProperty("checked", true);

    fireEvent.click(screen.getByRole("radio", { name: /^Sunday morning/ }));

    expect(draft()).toMatchObject({
      preset: "sunday_morning", transfer_volume: 30, train_headway_s: 480,
      onboard_load: 120, walking_mean_s: 110, max_hold_time: 120,
    });
    expect(slider(/Time between trains/).value).toBe("480");
    const conditions = screen.getByLabelText("Sunday morning conditions");
    expect(conditions.textContent).toContain("Train frequencyevery 480 s");
    expect(conditions.textContent).toContain("Maximum hold120 s");

    // A different preset replaces the shown conditions (#262)
    fireEvent.click(screen.getByRole("radio", { name: /^Weekday morning peak/ }));
    expect(screen.getByLabelText("Weekday morning peak conditions").textContent)
      .toContain("Train frequencyTimetable");
    expect(screen.queryByLabelText("Sunday morning conditions")).toBeNull();
  });

  it("says when a control was changed after picking a preset", () => {
    render(<Setup presets={[MORNING]} />);
    fireEvent.click(screen.getByRole("radio", { name: /^Weekday morning peak/ }));
    expect(screen.queryByText(/Some values were changed/)).toBeNull();

    fireEvent.change(slider(/Onboard load/), { target: { value: "200" } });

    expect(screen.getByText(/Some values were changed/)).toBeDefined();
    expect(draft().preset).toBe("weekday_morning");
  });

  it("goes back to the default window with Custom", () => {
    render(<Setup presets={[MORNING]} />);
    fireEvent.click(screen.getByRole("radio", { name: /^Weekday morning peak/ }));
    fireEvent.click(screen.getByRole("radio", { name: /^Custom/ }));

    expect(draft().preset).toBeNull();
    expect(draft().onboard_load).toBe(450);
  });
});

describe("Scenario setup through the API client", () => {
  beforeEach(() => useViewStore.setState({ activeView: "setup" }));
  afterEach(() => useViewStore.setState({ activeView: "station" }));

  it("loads the presets and sends the selected one with its values", async () => {
    const presetLoader = vi.fn(async () => [MORNING, SUNDAY]);
    const scenarioRunner: ScenarioRunner = vi.fn(async () => parseStationViewData(stationViewData));
    render(<App runLoader={null} scenarioRunner={scenarioRunner} presetLoader={presetLoader} />);

    fireEvent.click(await screen.findByRole("radio", { name: /^Sunday morning/ }));
    fireEvent.click(runButton());

    await waitFor(() => expect(scenarioRunner).toHaveBeenCalledTimes(1));
    const [, settings] = vi.mocked(scenarioRunner).mock.calls[0];
    expect(settings).toMatchObject({
      preset: "sunday_morning", transfer_volume: 30, train_headway_s: 480,
      onboard_load: 120, walking_mean_s: 110, max_hold_time: 120,
    });
  });

  it("explains a failed preset load and keeps the other settings usable", async () => {
    const presetLoader = vi.fn(async () => {
      throw new Error("Could not load the time-of-day presets (HTTP 503).");
    });
    render(<App runLoader={null} scenarioRunner={runner} presetLoader={presetLoader} />);

    expect(await screen.findByText("Could not load the time-of-day presets (HTTP 503).")).toBeDefined();
    expect(screen.getByRole("group", { name: "Conditions" })).toBeDefined();
  });
});
