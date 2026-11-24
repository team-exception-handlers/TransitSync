// AI contribution: 50% or more AI-generated
/**
 * Time-of-day presets (#261, #263): the API list is validated before use and
 * a preset turns into exactly the draft change its values describe.
 */
import { describe, expect, it, vi } from "vitest";
import {
  createPresetLoader,
  parseScenarioPresets,
  presetPatch,
  presetStartLabel,
} from "../../src/lib/scenario-presets";
import { MORNING } from "./preset-fixtures";

describe("parseScenarioPresets", () => {
  it("accepts the API's list unchanged", () => {
    expect(parseScenarioPresets([MORNING])).toStrictEqual([MORNING]);
  });

  it.each([
    ["a non-list body", { presets: [] }],
    ["a missing label", [{ ...MORNING, label: "" }]],
    ["a text number", [{ ...MORNING, conditions: { ...MORNING.conditions, onboard_load: "450" } }]],
    ["a non-finite headway", [{ ...MORNING, conditions: { ...MORNING.conditions, train_headway_s: Infinity } }]],
  ])("rejects %s", (_case, payload) => {
    expect(() => parseScenarioPresets(payload)).toThrow("Invalid scenario preset list");
  });
});

describe("createPresetLoader", () => {
  it("reads /scenario/presets and returns the validated list", async () => {
    const fetchImpl = vi.fn(async () => new Response(JSON.stringify([MORNING])));
    const presets = await createPresetLoader("http://api.test", fetchImpl)();

    expect(fetchImpl).toHaveBeenCalledWith("http://api.test/scenario/presets", expect.anything());
    expect(presets).toStrictEqual([MORNING]);
  });

  it("turns an HTTP failure into a sentence a user can read", async () => {
    const fetchImpl = vi.fn(async () => new Response("", { status: 503 }));

    await expect(createPresetLoader("http://api.test", fetchImpl)())
      .rejects.toThrow("Could not load the time-of-day presets (HTTP 503).");
  });
});

describe("presetPatch", () => {
  it("copies the name and all five values into the draft", () => {
    expect(presetPatch(MORNING)).toStrictEqual({
      preset: "weekday_morning",
      transfer_volume: 80,
      train_headway_s: null,
      onboard_load: 450,
      walking_mean_s: 130,
      max_hold_time: 60,
    });
  });

  it("keeps a preset's custom headway and treats a missing one as the timetable", () => {
    const custom = { ...MORNING, conditions: { ...MORNING.conditions, train_headway_s: 360 } };
    const missing = { ...MORNING, conditions: { ...MORNING.conditions, train_headway_s: undefined } };

    expect(presetPatch(custom).train_headway_s).toBe(360);
    expect(presetPatch(missing).train_headway_s).toBeNull();
  });

  it("labels the start without seconds", () => {
    expect(presetStartLabel(MORNING)).toBe("07:00");
  });
});
