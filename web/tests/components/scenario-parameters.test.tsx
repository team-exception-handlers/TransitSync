// AI contribution: 50% or more AI-generated
// @vitest-environment jsdom
/**
 * Scenario parameter controls on Scenario setup (#251 to #257): each control
 * shows and stores its value, and a bad typed value blocks the run and names
 * its setting.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { RunSettingsPanel } from "../../src/components/run-settings-panel";
import { connectionRuns } from "../../src/data/connection-runs";
import { stationViewData } from "../../src/data/stationViewData";
import { DEFAULT_RUN_SETTINGS } from "../../src/lib/run-settings";
import type { ScenarioRunner } from "../../src/lib/simulation-api";
import { parseStationViewData } from "../../src/lib/validateStationView";
import { usePlaybackStore } from "../../src/store/usePlaybackStore";
import { useRunSettingsStore } from "../../src/store/useRunSettingsStore";

const draft = () => useRunSettingsStore.getState().draft;
const slider = (name: RegExp) => screen.getByRole("slider", { name }) as HTMLInputElement;
const entry = (name: string) => screen.getByRole("spinbutton", { name }) as HTMLInputElement;
const runButton = () => screen.getByRole("button", { name: "Run scenario" }) as HTMLButtonElement;
const runner: ScenarioRunner = vi.fn(async () => parseStationViewData(stationViewData));

beforeEach(() => {
  useRunSettingsStore.setState({ draft: DEFAULT_RUN_SETTINGS, applied: {} });
  usePlaybackStore.getState().setAvailableRuns(connectionRuns);
  usePlaybackStore.getState().selectConnection("mcgill-rem-green");
});
afterEach(cleanup);

describe("parameter controls", () => {
  it("shows every default and puts the maximum hold on this screen", () => {
    render(<RunSettingsPanel runner={runner} />);
    const conditions = screen.getByRole("group", { name: "Conditions" });

    expect(within(conditions).getByText("60 passengers")).toBeDefined();
    expect(within(conditions).getByText("300 passengers")).toBeDefined();
    expect(within(conditions).getByText("120 s")).toBeDefined();
    expect(within(conditions).getByRole("slider", { name: /Maximum hold/ })).toBeDefined();
    expect(slider(/Onboard load/).max).toBe("800");
    expect(slider(/Walking time/).min).toBe("45");
  });

  it("stores a typed value once it is valid", () => {
    render(<RunSettingsPanel runner={runner} />);

    fireEvent.change(entry("Onboard load value"), { target: { value: "450" } });

    expect(draft().onboard_load).toBe(450);
    expect(slider(/Onboard load/).value).toBe("450");
  });

  it("blocks the run and names the setting while a typed value is invalid", () => {
    render(<RunSettingsPanel runner={runner} />);

    fireEvent.change(entry("Transfer volume value"), { target: { value: "250" } });

    // The bad value never reaches the store, so it can never be sent
    expect(draft().transfer_volume).toBe(60);
    expect(runButton().disabled).toBe(true);
    const alert = screen.getByRole("alert");
    expect(alert.textContent).toContain("Transfer volume: must be between 0 and 200");
    expect(entry("Transfer volume value").getAttribute("aria-invalid")).toBe("true");

    fireEvent.change(entry("Transfer volume value"), { target: { value: "90" } });

    expect(runButton().disabled).toBe(false);
    expect(screen.queryByRole("alert")).toBeNull();
    expect(draft().transfer_volume).toBe(90);
  });

  it("treats an empty box as invalid, and a slider move clears it", () => {
    render(<RunSettingsPanel runner={runner} />);

    fireEvent.change(entry("Walking time value"), { target: { value: "" } });
    expect(screen.getByRole("alert").textContent).toContain("Walking time: enter a number");

    fireEvent.change(slider(/Walking time/), { target: { value: "150" } });
    expect(screen.queryByRole("alert")).toBeNull();
    expect(entry("Walking time value").value).toBe("150");
  });

  it("switches train frequency between the timetable and a custom headway", () => {
    render(<RunSettingsPanel runner={runner} />);
    expect(screen.queryByRole("slider", { name: /Time between trains/ })).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Custom" }));
    expect(draft().train_headway_s).toBe(180);
    fireEvent.change(slider(/Time between trains/), { target: { value: "300" } });
    expect(draft().train_headway_s).toBe(300);

    fireEvent.click(screen.getByRole("button", { name: "Timetable" }));
    expect(draft().train_headway_s).toBeNull();
    expect(screen.queryByRole("slider", { name: /Time between trains/ })).toBeNull();
  });

  it("drops a bad headway entry when switching back to Timetable", () => {
    render(<RunSettingsPanel runner={runner} />);
    fireEvent.click(screen.getByRole("button", { name: "Custom" }));

    fireEvent.change(entry("Time between trains value"), { target: { value: "125" } });
    expect(runButton().disabled).toBe(true);

    fireEvent.click(screen.getByRole("button", { name: "Timetable" }));

    // The slider is gone, so its error must not keep blocking the run
    expect(screen.queryByRole("alert")).toBeNull();
    expect(runButton().disabled).toBe(false);
  });

  it("clears a bad typed value on Reset even when the stored value is the default", () => {
    render(<RunSettingsPanel runner={runner} />);

    fireEvent.change(entry("Transfer volume value"), { target: { value: "250" } });
    expect(draft().transfer_volume).toBe(60);
    expect(runButton().disabled).toBe(true);

    fireEvent.click(screen.getByRole("button", { name: "Reset to defaults" }));

    expect(entry("Transfer volume value").value).toBe("60");
    expect(screen.queryByRole("alert")).toBeNull();
    expect(runButton().disabled).toBe(false);
  });
});
