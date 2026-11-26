// AI contribution: 50% or more AI-generated
/** The Compare screen's store loads both runs together and keeps only the newest pair (US-4.1). */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { stationViewData } from "../../src/data/stationViewData";
import { DEFAULT_RUN_SETTINGS } from "../../src/lib/run-settings";
import type { ComparisonRunner, SimulationComparison } from "../../src/lib/simulation-api";
import { EMPTY_COMPARISON, useComparisonStore } from "../../src/store/useComparisonStore";

const CONNECTION = "mcgill-rem-green";

/** A pair whose holding side is told apart from the baseline by its duration. */
function pairFor(strategy: string, holdingDuration = 360): SimulationComparison {
  return {
    holding: { ...stationViewData, duration_s: holdingDuration },
    noHolding: stationViewData,
    holdingStrategy: strategy,
    startingConditions: { serviceDate: "2026-10-05", masterSeed: 42, duration_s: 360 },
    passengerSplit: {
      better_off: 3, worse_off: 1, unaffected: 10, not_compared: 0,
      left_in_one_run: 0, unaffected_threshold_s: 30,
      total_time_saved_s: 300, total_time_lost_s: 40,
      average_time_saved_s: 100, average_time_lost_s: 40,
    },
  };
}

/** A runner whose calls resolve only when the test says so. */
function deferredRunner() {
  const pending: { resolve: (pair: SimulationComparison) => void; reject: (error: Error) => void }[] = [];
  const runner = vi.fn<ComparisonRunner>(() => new Promise((resolve, reject) => {
    pending.push({ resolve, reject });
  }));
  return { runner, pending };
}

const load = (runner: ComparisonRunner, settings = DEFAULT_RUN_SETTINGS, signal?: AbortSignal) =>
  useComparisonStore.getState().loadComparison(CONNECTION, settings, runner, signal);

beforeEach(() => {
  useComparisonStore.setState(EMPTY_COMPARISON);
});

describe("useComparisonStore", () => {
  it("loads both runs from one runner call", async () => {
    const runner = vi.fn<ComparisonRunner>(async () => pairFor("connection_protection"));

    expect(await load(runner)).toBe(true);

    expect(runner).toHaveBeenCalledTimes(1);
    const state = useComparisonStore.getState();
    expect(state.status).toBe("ready");
    expect(state.holding).not.toBe(state.noHolding);
    expect(state.holdingStrategy).toBe("connection_protection");
    expect(state.startingConditions?.masterSeed).toBe(42);
    expect(state.passengerSplit?.better_off).toBe(3);
    expect(state.connectionId).toBe(CONNECTION);
  });

  it("does not refetch a pair already loaded for the same request", async () => {
    const runner = vi.fn<ComparisonRunner>(async () => pairFor("connection_protection"));
    await load(runner);

    // A copy with equal values sends the same body, so it is the same key.
    expect(await load(runner, { ...DEFAULT_RUN_SETTINGS })).toBe(false);
    expect(runner).toHaveBeenCalledTimes(1);

    await load(runner, { ...DEFAULT_RUN_SETTINGS, passenger_flow: "High" });
    expect(runner).toHaveBeenCalledTimes(2);
  });

  it("drops a response overtaken by a newer request", async () => {
    const { runner, pending } = deferredRunner();
    const first = load(runner);
    const second = load(runner, { ...DEFAULT_RUN_SETTINGS, passenger_flow: "High" });

    pending[1].resolve(pairFor("newer", 300));
    pending[0].resolve(pairFor("older", 200));

    expect(await second).toBe(true);
    expect(await first).toBe(false);
    expect(useComparisonStore.getState().holdingStrategy).toBe("newer");
    expect(useComparisonStore.getState().holding?.duration_s).toBe(300);
  });

  it("drops a response whose request was aborted", async () => {
    const { runner, pending } = deferredRunner();
    const controller = new AbortController();
    const result = load(runner, DEFAULT_RUN_SETTINGS, controller.signal);

    controller.abort();
    pending[0].resolve(pairFor("connection_protection"));

    expect(await result).toBe(false);
    expect(useComparisonStore.getState().holding).toBeNull();
    // Nothing is loading any more and there is no pair to fall back to.
    expect(useComparisonStore.getState().status).toBe("idle");
  });

  it("is ready again when an aborted load is followed by a request for the pair shown", async () => {
    await load(vi.fn<ComparisonRunner>(async () => pairFor("connection_protection")));
    const shown = useComparisonStore.getState().holding;

    // The user changes settings, then leaves Compare before the runs return.
    const { runner, pending } = deferredRunner();
    const controller = new AbortController();
    const abandoned = load(runner, { ...DEFAULT_RUN_SETTINGS, passenger_flow: "High" }, controller.signal);
    expect(useComparisonStore.getState().status).toBe("loading");
    controller.abort();
    pending[0].reject(new DOMException("Aborted", "AbortError"));
    expect(await abandoned).toBe(false);
    expect(useComparisonStore.getState().status).toBe("ready");

    // Coming back with the original settings reuses the pair without a fetch.
    const reuse = vi.fn<ComparisonRunner>();
    expect(await load(reuse)).toBe(false);
    expect(reuse).not.toHaveBeenCalled();
    expect(useComparisonStore.getState().status).toBe("ready");
    expect(useComparisonStore.getState().holding).toBe(shown);
  });

  it("reusing the pair shown clears a loading status and drops the load in flight", async () => {
    await load(vi.fn<ComparisonRunner>(async () => pairFor("connection_protection")));
    const shown = useComparisonStore.getState().holding;

    // A load for other settings is still running when the original ones come back.
    const { runner, pending } = deferredRunner();
    const inFlight = load(runner, { ...DEFAULT_RUN_SETTINGS, passenger_flow: "High" });
    expect(await load(runner)).toBe(false);
    expect(useComparisonStore.getState().status).toBe("ready");

    pending[0].resolve(pairFor("stale", 200));
    expect(await inFlight).toBe(false);
    expect(useComparisonStore.getState().holding).toBe(shown);
    expect(useComparisonStore.getState().status).toBe("ready");
  });

  it("reusing the pair shown clears an earlier failure", async () => {
    await load(vi.fn<ComparisonRunner>(async () => pairFor("connection_protection")));
    const failing = vi.fn<ComparisonRunner>(async () => { throw new Error("Server down"); });
    await load(failing, { ...DEFAULT_RUN_SETTINGS, passenger_flow: "Low" });

    expect(await load(failing)).toBe(false);
    expect(useComparisonStore.getState()).toMatchObject({ status: "ready", error: null });
  });

  it("is idle, not ready, when a load for another connection is aborted", async () => {
    await load(vi.fn<ComparisonRunner>(async () => pairFor("connection_protection")));

    // The user switches connection, then leaves Compare before the runs return.
    const { runner, pending } = deferredRunner();
    const controller = new AbortController();
    const abandoned = useComparisonStore.getState()
      .loadComparison("edouard_montpetit-rem-blue", DEFAULT_RUN_SETTINGS, runner, controller.signal);
    controller.abort();
    pending[0].reject(new DOMException("Aborted", "AbortError"));

    expect(await abandoned).toBe(false);
    // The stored pair is for the old connection, so the screen hides it and
    // "ready" would describe runs the user cannot see.
    expect(useComparisonStore.getState().connectionId).toBe(CONNECTION);
    expect(useComparisonStore.getState().status).toBe("idle");
  });

  it("keeps the previous pair and reports the error when a load fails", async () => {
    await load(vi.fn<ComparisonRunner>(async () => pairFor("connection_protection")));
    const shown = useComparisonStore.getState().holding;

    const failing = vi.fn<ComparisonRunner>(async () => { throw new Error("Server down"); });
    expect(await load(failing, { ...DEFAULT_RUN_SETTINGS, passenger_flow: "Low" })).toBe(false);

    const state = useComparisonStore.getState();
    expect(state.status).toBe("error");
    expect(state.error).toBe("Server down");
    expect(state.holding).toBe(shown);
  });
});
