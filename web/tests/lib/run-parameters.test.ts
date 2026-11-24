// AI contribution: 50% or more AI-generated
/**
 * Scenario parameters in the run settings (#252 to #257, #267): ranges,
 * typed-value checks, and the exact request body the API receives.
 */
import { describe, expect, expectTypeOf, it } from "vitest";
import {
  DEFAULT_RUN_SETTINGS,
  ONBOARD_LOAD_RANGE,
  TRAIN_HEADWAY_RANGE,
  TRANSFER_VOLUME_RANGE,
  WALKING_TIME_RANGE,
  applyRunSettings,
  buildRunRequest,
  formatHeadway,
  validateSetting,
} from "../../src/lib/run-settings";
import type { components } from "../../src/types/api.generated";

describe("validateSetting", () => {
  it("accepts both range ends", () => {
    expect(validateSetting("Transfer volume", 0, TRANSFER_VOLUME_RANGE)).toBeNull();
    expect(validateSetting("Transfer volume", 200, TRANSFER_VOLUME_RANGE)).toBeNull();
  });

  it.each([
    [201, TRANSFER_VOLUME_RANGE, "Transfer volume: must be between 0 and 200"],
    [-10, ONBOARD_LOAD_RANGE, "Onboard load: must be between 0 and 800"],
    [305, ONBOARD_LOAD_RANGE, "Onboard load: must be in steps of 10"],
    [130, TRAIN_HEADWAY_RANGE, "Train frequency: must be in steps of 30"],
    [Number.NaN, WALKING_TIME_RANGE, "Walking time: enter a number"],
  ])("names the setting for %s", (value, range, message) => {
    const label = message.split(":")[0];
    expect(validateSetting(label, value, range)).toBe(message);
  });
});

describe("applyRunSettings for scenario parameters", () => {
  it("clamps and snaps every parameter into the API's range", () => {
    const next = applyRunSettings(DEFAULT_RUN_SETTINGS, {
      transfer_volume: 999, train_headway_s: 100, onboard_load: 304, walking_mean_s: 10,
    });

    expect(next.transfer_volume).toBe(200);
    expect(next.train_headway_s).toBe(120);
    expect(next.onboard_load).toBe(300);
    expect(next.walking_mean_s).toBe(45);
  });

  it("keeps null as the timetable and a bad number as the current value", () => {
    const custom = applyRunSettings(DEFAULT_RUN_SETTINGS, { train_headway_s: 240 });

    expect(applyRunSettings(custom, { train_headway_s: null }).train_headway_s).toBeNull();
    expect(applyRunSettings(custom, { onboard_load: Number.NaN }).onboard_load).toBe(300);
  });
});

describe("buildRunRequest with scenario parameters", () => {
  it("leaves out the headway and preset while they are unset", () => {
    const body = buildRunRequest("c", DEFAULT_RUN_SETTINGS);

    expect("train_headway_s" in body).toBe(false);
    expect("preset" in body).toBe(false);
    expect([body.transfer_volume, body.onboard_load, body.walking_mean_s]).toStrictEqual([60, 300, 120]);
  });

  it("sends the shown values, so the display and the run always agree", () => {
    const settings = applyRunSettings(DEFAULT_RUN_SETTINGS, {
      preset: "sunday_morning", transfer_volume: 30, train_headway_s: 480, onboard_load: 120,
      walking_mean_s: 110, max_hold_time: 120,
    });
    const body = buildRunRequest("c", settings);

    expect(body).toMatchObject({
      preset: "sunday_morning", transfer_volume: 30, train_headway_s: 480, onboard_load: 120,
      walking_mean_s: 110, max_hold_time: 120,
    });
  });

  it("returns the request type generated from the API schema", () => {
    // Fails `tsc` and this test if the backend model and the client drift (#267)
    expectTypeOf(buildRunRequest).returns
      .toEqualTypeOf<components["schemas"]["SimulationRunRequest"]>();
  });
});

describe("formatHeadway", () => {
  it("shows the timetable or the chosen gap", () => {
    expect(formatHeadway(null)).toBe("Timetable");
    expect(formatHeadway(240)).toBe("every 240 s");
  });
});
