// AI contribution: 50% or more AI-generated
/** The run settings store only ever holds values the API accepts. */
import { beforeEach, describe, expect, it } from "vitest";
import { DEFAULT_RUN_SETTINGS } from "../../src/lib/run-settings";
import { useRunSettingsStore } from "../../src/store/useRunSettingsStore";

const store = () => useRunSettingsStore.getState();

describe("useRunSettingsStore", () => {
  beforeEach(() => {
    useRunSettingsStore.setState({ draft: DEFAULT_RUN_SETTINGS, applied: {} });
  });

  it("starts on the backend defaults", () => {
    expect(store().draft).toStrictEqual({
      strategy: "no_control",
      max_hold_time: 300,
      irregularity_threshold: 0.25,
      error_magnitude: 1,
      passenger_flow: "Normal",
      disruption_enabled: false,
    });
  });

  it.each([
    [-0.1, 0],
    [0, 0],
    [3, 3],
    [3.1, 3],
  ])("stores a requested error magnitude of %d as %d", (requested, stored) => {
    store().update({ error_magnitude: requested });

    expect(store().draft.error_magnitude).toBe(stored);
  });

  it.each([
    [0, 5],
    [5, 5],
    [300, 300],
    [305, 300],
    [47, 45],
  ])("stores a requested maximum hold of %d s as %d s", (requested, stored) => {
    store().update({ max_hold_time: requested });

    expect(store().draft.max_hold_time).toBe(stored);
  });

  it("keeps the other settings when one control changes", () => {
    store().update({ strategy: "adaptive" });
    store().update({ irregularity_threshold: 0.4 });

    expect(store().draft).toStrictEqual({
      ...DEFAULT_RUN_SETTINGS,
      strategy: "adaptive",
      irregularity_threshold: 0.4,
    });
  });

  it("resets every control to the backend defaults", () => {
    store().update({ strategy: "rolling_horizon", max_hold_time: 60, irregularity_threshold: 0.9,
      error_magnitude: 0, passenger_flow: "High", disruption_enabled: true });
    store().reset();

    expect(store().draft).toStrictEqual(DEFAULT_RUN_SETTINGS);
  });

  it("records applied settings per connection without following later edits", () => {
    store().update({ strategy: "connection_protection", max_hold_time: 45 });
    store().markApplied("mcgill-rem-green", store().draft);
    store().update({ max_hold_time: 120 });

    expect(store().applied["mcgill-rem-green"].max_hold_time).toBe(45);
    expect(store().applied["edouard_montpetit-rem-blue"]).toBeUndefined();
  });
});
