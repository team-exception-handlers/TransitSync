// AI contribution: 50% or more AI-generated
/** Run settings: ranges, defaults and the exact request body the API accepts. */
import { describe, expect, it } from "vitest";
import {
  DEFAULT_RUN_SETTINGS,
  MAX_HOLD_RANGE,
  STRATEGY_OPTIONS,
  THRESHOLD_RANGE,
  applyRunSettings,
  buildRunRequest,
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

describe("buildRunRequest", () => {
  it("matches the backend defaults and omits the threshold key for non-adaptive runs", () => {
    const body = buildRunRequest("mcgill-rem-green", DEFAULT_RUN_SETTINGS);

    expect(body).toStrictEqual({
      connection_id: "mcgill-rem-green",
      strategy: "no_control",
      max_hold_time: 300,
    });
    // The API rejects the key even when its value is null, so it must be absent.
    expect("irregularity_threshold" in body).toBe(false);
    expect(JSON.stringify(body)).not.toContain("irregularity_threshold");
  });

  it.each(STRATEGY_OPTIONS.filter((option) => option.name !== "adaptive"))(
    "omits the threshold for $name", ({ name }) => {
      const body = buildRunRequest("c", { ...DEFAULT_RUN_SETTINGS, strategy: name });

      expect(Object.keys(body)).toStrictEqual(["connection_id", "strategy", "max_hold_time"]);
    });

  it("includes the threshold as a number for adaptive", () => {
    const body = buildRunRequest("c", {
      strategy: "adaptive", max_hold_time: 60, irregularity_threshold: 0.4,
    });

    expect(JSON.parse(JSON.stringify(body))).toStrictEqual({
      connection_id: "c",
      strategy: "adaptive",
      max_hold_time: 60,
      irregularity_threshold: 0.4,
    });
  });

  it("sends strict JSON types: strings and numbers, never numeric strings", () => {
    const body = buildRunRequest("c", { ...DEFAULT_RUN_SETTINGS, strategy: "adaptive" });

    expect(typeof body.connection_id).toBe("string");
    expect(typeof body.strategy).toBe("string");
    expect(typeof body.max_hold_time).toBe("number");
    expect(typeof body.irregularity_threshold).toBe("number");
  });
});
