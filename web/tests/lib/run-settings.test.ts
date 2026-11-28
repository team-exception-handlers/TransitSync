// AI contribution: 50% or more AI-generated
/** Run settings: ranges, defaults and the exact request body the API accepts. */
import { describe, expect, it } from "vitest";
import {
  DEFAULT_RUN_SETTINGS,
  DEFAULT_DISRUPTION_MAGNITUDES,
  ERROR_MAGNITUDE_RANGE,
  HEADWAY_IRREGULARITY_RANGE,
  MAX_HOLD_RANGE,
  STRATEGY_OPTIONS,
  THRESHOLD_RANGE,
  applyRunSettings,
  buildRunRequest,
  formatErrorMagnitude,
  formatHeadwayIrregularity,
  snapToRange,
} from "../../src/lib/run-settings";

// The registry module is the backend's one list of strategies; each class
// it registers declares its name in its own file.
const strategySources = import.meta.glob<string>(
  "../../../simulator/control/strategies/*.py",
  { query: "?raw", import: "default", eager: true },
);

/** Strategy names declared by the Python strategy classes, sorted. */
function backendStrategyNames(): string[] {
  const names = Object.values(strategySources).flatMap((source) =>
    [...source.matchAll(/^ {4}name(?:: ClassVar\[str\])? = "(\w+)"/gm)].map((match) => match[1]));
  return names.toSorted((a, b) => a.localeCompare(b));
}

// The request model is the contract; its field names are read from the source.
const requestModelSource = Object.values(import.meta.glob<string>(
  "../../../api/simulation_run.py", { query: "?raw", import: "default", eager: true }))[0];

/** Field names declared on the API's SimulationRunRequest model, sorted. */
function backendRequestFields(): string[] {
  const start = requestModelSource.indexOf("class SimulationRunRequest");
  const end = requestModelSource.indexOf("@model_validator", start);
  const fields = [...requestModelSource.slice(start, end).matchAll(/^ {4}(\w+): /gm)]
    .map((match) => match[1]);
  return fields.toSorted((a, b) => a.localeCompare(b));
}

describe("strategy options", () => {
  it("lists exactly the strategies the backend registers", () => {
    const offered = STRATEGY_OPTIONS.map((option) => option.name)
      .toSorted((a, b) => a.localeCompare(b));

    expect(backendStrategyNames()).toHaveLength(6);
    expect(offered).toStrictEqual(backendStrategyNames());
  });

  it("shows the mockup's Coordinated card for rolling_horizon", () => {
    const coordinated = STRATEGY_OPTIONS.find((option) => option.label === "Coordinated");

    expect(coordinated?.name).toBe("rolling_horizon");
  });
});

describe("snapToRange", () => {
  it.each([
    [0, 5],
    [5, 5],
    [300, 300],
    [305, 300],
    [47, 45],
    [48, 50],
  ])("brings a maximum hold of %d s to %d s", (requested, expected) => {
    expect(snapToRange(requested, MAX_HOLD_RANGE, 300)).toBe(expected);
  });

  it.each([
    [-0.1, 0],
    [0.15, 0.15],
    [0.26, 0.25],
    [1.2, 1],
  ])("brings a threshold of %d to %d without binary noise", (requested, expected) => {
    expect(snapToRange(requested, THRESHOLD_RANGE, 0.25)).toBe(expected);
  });

  it.each([
    [-0.1, 0],
    [0, 0],
    [1.26, 1.3],
    [3, 3],
    [3.1, 3],
  ])("brings an error magnitude of %d to %d", (requested, expected) => {
    expect(snapToRange(requested, ERROR_MAGNITUDE_RANGE, 1)).toBe(expected);
  });

  it("keeps the current value when the input is not a finite number", () => {
    expect(snapToRange(Number.NaN, MAX_HOLD_RANGE, 120)).toBe(120);
    expect(snapToRange(Number.POSITIVE_INFINITY, MAX_HOLD_RANGE, 120)).toBe(120);
  });
});

describe("applyRunSettings", () => {
  it("normalises a patched number and leaves the other fields alone", () => {
    const next = applyRunSettings(DEFAULT_RUN_SETTINGS, { max_hold_time: 47 });

    expect(next).toStrictEqual({ ...DEFAULT_RUN_SETTINGS, max_hold_time: 45 });
  });

  it("ignores a strategy the backend does not register", () => {
    const patch = { strategy: "teleport" } as unknown as Partial<typeof DEFAULT_RUN_SETTINGS>;

    expect(applyRunSettings(DEFAULT_RUN_SETTINGS, patch).strategy).toBe("no_control");
  });
});

describe("applyRunSettings for run conditions", () => {
  it("accepts scenario parameters inside their ranges and the disruption switch", () => {
    const next = applyRunSettings(DEFAULT_RUN_SETTINGS, {
      transfer_volume: 80, train_headway_s: 240, onboard_load: 450, walking_mean_s: 150,
      disruption_enabled: true, error_magnitude: 0,
    });

    expect([next.transfer_volume, next.train_headway_s, next.onboard_load, next.walking_mean_s])
      .toStrictEqual([80, 240, 450, 150]);
    expect(next.disruption_enabled).toBe(true);
    expect(next.error_magnitude).toBe(0);
  });

  it("keeps the current preset and switch when a value is not one the API accepts", () => {
    const patch = { preset: 7, disruption_enabled: "yes" } as unknown as
      Partial<typeof DEFAULT_RUN_SETTINGS>;
    const next = applyRunSettings(DEFAULT_RUN_SETTINGS, patch);

    expect(next.preset).toBeNull();
    expect(next.disruption_enabled).toBe(false);
  });

  it("uses a unitless CV magnitude for uneven headways and seconds otherwise", () => {
    const uneven = applyRunSettings(DEFAULT_RUN_SETTINGS, {
      disruption_preset: "uneven_headways",
    });
    const adjusted = applyRunSettings(uneven, { disruption_magnitude: 0.47 });
    const platformDelay = applyRunSettings(adjusted, {
      disruption_preset: "platform_delay",
    });

    expect(uneven.disruption_magnitude)
      .toBe(DEFAULT_DISRUPTION_MAGNITUDES.uneven_headways);
    expect(adjusted.disruption_magnitude).toBe(0.45);
    expect(platformDelay.disruption_magnitude).toBe(60);
    expect(HEADWAY_IRREGULARITY_RANGE).toStrictEqual({ min: 0.05, max: 1, step: 0.05 });
    expect(formatHeadwayIrregularity(0.3)).toBe("0.30 CV");
  });
});

describe("formatErrorMagnitude", () => {
  it("labels zero as the upper bound with perfect information", () => {
    expect(formatErrorMagnitude(0)).toBe("0.0 · upper bound (perfect information)");
  });

  it("shows any other value with one decimal and no label", () => {
    expect(formatErrorMagnitude(1)).toBe("1.0");
    expect(formatErrorMagnitude(3)).toBe("3.0");
  });
});

describe("buildRunRequest", () => {
  it("uses exactly the API's field names when every field is sent", () => {
    const body = buildRunRequest("c", {
      ...DEFAULT_RUN_SETTINGS, strategy: "adaptive", train_headway_s: 240,
      preset: "weekday_morning",
    });
    const sent = Object.keys(body).toSorted((a, b) => a.localeCompare(b));

    expect(backendRequestFields()).toHaveLength(14);
    expect(sent).toStrictEqual(backendRequestFields());
  });

  it("matches the backend defaults and omits the threshold key for non-adaptive runs", () => {
    const body = buildRunRequest("mcgill-rem-green", DEFAULT_RUN_SETTINGS);

    expect(body).toStrictEqual({
      connection_id: "mcgill-rem-green",
      strategy: "no_control",
      max_hold_time: 300,
      error_magnitude: 1,
      transfer_volume: 60,
      onboard_load: 300,
      walking_mean_s: 120,
      disruption_enabled: false,
      disruption_preset: "none",
      disruption_time_s: 120,
      disruption_magnitude: 60,
    });
    // The API rejects the key even when its value is null, so it must be absent.
    expect("irregularity_threshold" in body).toBe(false);
    expect(JSON.stringify(body)).not.toContain("irregularity_threshold");
  });

  it.each(STRATEGY_OPTIONS.filter((option) => option.name !== "adaptive"))(
    "omits the threshold for $name", ({ name }) => {
      const body = buildRunRequest("c", { ...DEFAULT_RUN_SETTINGS, strategy: name });

      expect(Object.keys(body)).toStrictEqual(["connection_id", "strategy", "max_hold_time",
        "error_magnitude", "transfer_volume", "onboard_load", "walking_mean_s",
        "disruption_enabled", "disruption_preset",
        "disruption_time_s", "disruption_magnitude"]);
    });

  it("includes the threshold as a number for adaptive", () => {
    const body = buildRunRequest("c", {
      ...DEFAULT_RUN_SETTINGS, strategy: "adaptive", max_hold_time: 60,
      irregularity_threshold: 0.4, error_magnitude: 0, transfer_volume: 80,
      disruption_enabled: true, disruption_preset: undefined,
      disruption_time_s: undefined, disruption_magnitude: undefined,
    });

    expect(JSON.parse(JSON.stringify(body))).toStrictEqual({
      connection_id: "c",
      strategy: "adaptive",
      max_hold_time: 60,
      error_magnitude: 0,
      transfer_volume: 80,
      onboard_load: 300,
      walking_mean_s: 120,
      disruption_enabled: true,
      disruption_preset: "none",
      disruption_time_s: 120,
      disruption_magnitude: 60,
      irregularity_threshold: 0.4,
    });
  });

  it("sends strict JSON types: strings, numbers and a boolean, never numeric strings", () => {
    const body = buildRunRequest("c", { ...DEFAULT_RUN_SETTINGS, strategy: "adaptive" });

    expect(typeof body.connection_id).toBe("string");
    expect(typeof body.strategy).toBe("string");
    expect(typeof body.max_hold_time).toBe("number");
    expect(typeof body.irregularity_threshold).toBe("number");
    expect(typeof body.error_magnitude).toBe("number");
    expect(typeof body.transfer_volume).toBe("number");
    expect(typeof body.onboard_load).toBe("number");
    expect(typeof body.disruption_enabled).toBe("boolean");
  });
});
