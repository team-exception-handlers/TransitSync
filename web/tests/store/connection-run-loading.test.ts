// AI contribution: 50% or more AI-generated
/**
 * Loading a selected connection's run output into the shared store (#79):
 * the run replaces the mock, playback restarts, and stale or failed loads
 * never overwrite the connection the user is looking at.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { connectionRuns } from "../../src/data/connection-runs";
import { stationViewData } from "../../src/data/stationViewData";
import { parseStationViewData } from "../../src/lib/validateStationView";
import { usePlaybackStore } from "../../src/store/usePlaybackStore";
import type { StationViewData } from "../../src/types/stationView";

const MCGILL = "mcgill-rem-green";
const BONAVENTURE = "gare_centrale_bonaventure-rem-orange";

// A run that is valid but distinguishable from the McGill mock.
function simulatedRun(source: StationViewData = stationViewData): StationViewData {
  const run = structuredClone(source);
  run.interchange.name = `${source.interchange.name} (simulated)`;
  run.duration_s = 600;
  return parseStationViewData(run);
}

// A promise the test resolves by hand, to order responses after selections.
function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((res, rej) => { resolve = res; reject = rej; });
  return { promise, resolve, reject };
}

describe("loadConnectionRun", () => {
  beforeEach(() => {
    const store = usePlaybackStore.getState();
    store.setAvailableRuns(connectionRuns);
    store.loadData(stationViewData);
    usePlaybackStore.setState({ runStatus: "mock", runError: null });
  });

  it("shows the loaded run from 0 s, paused, and marks it as simulator output", async () => {
    const run = simulatedRun();
    usePlaybackStore.getState().seek(120);
    usePlaybackStore.getState().play();

    await usePlaybackStore.getState().loadConnectionRun(MCGILL, async () => run);

    const state = usePlaybackStore.getState();
    expect(state.data).toBe(run);
    expect(state.currentTime_s).toBe(0);
    expect(state.anchorTime_s).toBe(0);
    expect(state.isPlaying).toBe(false);
    expect(state.runStatus).toBe("simulated");
    expect(state.selectedConnectionId).toBe(MCGILL);
  });

  it("replaces the mock catalog entry in place, keeping selector order", async () => {
    const run = simulatedRun();
    await usePlaybackStore.getState().loadConnectionRun(MCGILL, async () => run);

    const runs = usePlaybackStore.getState().availableRuns;
    expect(runs).toHaveLength(3);
    // McGill is the middle mock run in connection-runs.ts.
    expect(runs[1]).toBe(run);
    expect(runs.map((item) => item.connections[0].id))
      .toStrictEqual([BONAVENTURE, MCGILL, "edouard_montpetit-rem-blue"]);
  });

  it("reuses loaded output when the user comes back to a connection", async () => {
    const run = simulatedRun();
    const loader = vi.fn(async () => run);
    const store = usePlaybackStore.getState();
    await store.loadConnectionRun(MCGILL, loader);
    store.selectConnection(BONAVENTURE);
    expect(usePlaybackStore.getState().runStatus).toBe("mock");

    store.selectConnection(MCGILL);
    await store.loadConnectionRun(MCGILL, loader);

    expect(loader).toHaveBeenCalledTimes(1);
    expect(usePlaybackStore.getState().data).toBe(run);
    expect(usePlaybackStore.getState().runStatus).toBe("simulated");
  });

  it("drops a response that arrives after the user picked another connection", async () => {
    const pending = deferred<StationViewData>();
    const store = usePlaybackStore.getState();
    const load = store.loadConnectionRun(MCGILL, () => pending.promise);
    expect(usePlaybackStore.getState().runStatus).toBe("loading");

    store.selectConnection(BONAVENTURE);
    usePlaybackStore.getState().seek(45);
    pending.resolve(simulatedRun());
    await load;

    const state = usePlaybackStore.getState();
    expect(state.selectedConnectionId).toBe(BONAVENTURE);
    expect(state.data?.interchange.id).toBe("gare_centrale_bonaventure");
    expect(state.currentTime_s).toBe(45);
    expect(state.simulatedConnectionIds).toStrictEqual([]);
  });

  it("drops a response whose request was aborted", async () => {
    const controller = new AbortController();
    const pending = deferred<StationViewData>();
    const load = usePlaybackStore.getState()
      .loadConnectionRun(MCGILL, () => pending.promise, controller.signal);

    controller.abort();
    pending.resolve(simulatedRun());
    await load;

    expect(usePlaybackStore.getState().data?.duration_s).toBe(stationViewData.duration_s);
  });

  it("keeps the mock run and position when the load fails, and reports why", async () => {
    usePlaybackStore.getState().seek(90);

    await usePlaybackStore.getState().loadConnectionRun(MCGILL, async () => {
      throw new Error("Unknown connection: mcgill-rem-green");
    });

    const state = usePlaybackStore.getState();
    expect(state.runStatus).toBe("error");
    expect(state.runError).toBe("Unknown connection: mcgill-rem-green");
    expect(state.data?.duration_s).toBe(stationViewData.duration_s);
    expect(state.currentTime_s).toBe(90);
  });

  it("ignores a failure for a connection the user already left", async () => {
    const pending = deferred<StationViewData>();
    const load = usePlaybackStore.getState().loadConnectionRun(MCGILL, () => pending.promise);
    usePlaybackStore.getState().selectConnection(BONAVENTURE);

    pending.reject(new Error("network down"));
    await load;

    expect(usePlaybackStore.getState().runStatus).toBe("mock");
    expect(usePlaybackStore.getState().runError).toBeNull();
  });

  it("does not request a connection that is not selected", async () => {
    const loader = vi.fn(async () => simulatedRun());
    await usePlaybackStore.getState().loadConnectionRun(BONAVENTURE, loader);

    expect(loader).not.toHaveBeenCalled();
    expect(usePlaybackStore.getState().runStatus).toBe("mock");
  });

  it("forgets simulator output when a new catalog is registered", async () => {
    await usePlaybackStore.getState().loadConnectionRun(MCGILL, async () => simulatedRun());
    usePlaybackStore.getState().setAvailableRuns(connectionRuns);

    expect(usePlaybackStore.getState().simulatedConnectionIds).toStrictEqual([]);
  });
});

describe("loadConnectionRun with rerun (run settings panel)", () => {
  beforeEach(() => {
    const store = usePlaybackStore.getState();
    store.setAvailableRuns(connectionRuns);
    store.loadData(stationViewData);
    usePlaybackStore.setState({ runStatus: "mock", runError: null });
  });

  it("reuses loaded output by default but replaces it when rerun is set", async () => {
    const store = usePlaybackStore.getState();
    const first = simulatedRun();
    const second = simulatedRun();
    second.duration_s = 900;

    expect(await store.loadConnectionRun(MCGILL, async () => first)).toBe(true);
    const reused = vi.fn(async () => second);
    expect(await store.loadConnectionRun(MCGILL, reused)).toBe(false);
    expect(reused).not.toHaveBeenCalled();

    expect(await store.loadConnectionRun(MCGILL, async () => second, undefined, { rerun: true })).toBe(true);
    expect(usePlaybackStore.getState().data?.duration_s).toBe(900);
    expect(usePlaybackStore.getState().simulatedConnectionIds).toStrictEqual([MCGILL]);
  });

  it("keeps the newer rerun when two reruns resolve in reverse order", async () => {
    const store = usePlaybackStore.getState();
    const older = deferred<StationViewData>();
    const newer = deferred<StationViewData>();
    const olderRun = simulatedRun();
    olderRun.duration_s = 600;
    const newerRun = simulatedRun();
    newerRun.duration_s = 900;
    const rerun = { rerun: true };
    const olderLoad = store.loadConnectionRun(MCGILL, () => older.promise, undefined, rerun);
    const newerLoad = store.loadConnectionRun(MCGILL, () => newer.promise, undefined, rerun);

    newer.resolve(newerRun);
    expect(await newerLoad).toBe(true);
    older.resolve(olderRun);

    expect(await olderLoad).toBe(false);
    expect(usePlaybackStore.getState().data?.duration_s).toBe(900);
    expect(usePlaybackStore.getState().runStatus).toBe("simulated");
  });

  it("ignores an older rerun's failure that arrives after a newer rerun succeeded", async () => {
    const store = usePlaybackStore.getState();
    const older = deferred<StationViewData>();
    const rerun = { rerun: true };
    const olderLoad = store.loadConnectionRun(MCGILL, () => older.promise, undefined, rerun);
    await store.loadConnectionRun(MCGILL, async () => simulatedRun(), undefined, rerun);

    older.reject(new Error("The simulation run failed on the server (HTTP 500)."));

    expect(await olderLoad).toBe(false);
    expect(usePlaybackStore.getState().runStatus).toBe("simulated");
    expect(usePlaybackStore.getState().runError).toBeNull();
  });

  it("does not let a reused load cancel a rerun in flight", async () => {
    const store = usePlaybackStore.getState();
    await store.loadConnectionRun(MCGILL, async () => simulatedRun());
    const pending = deferred<StationViewData>();
    const rerunLoad = store.loadConnectionRun(MCGILL, () => pending.promise, undefined, { rerun: true });
    // Same connection without rerun: reuses the loaded output and loads nothing.
    expect(await store.loadConnectionRun(MCGILL, async () => simulatedRun())).toBe(false);

    const rerunRun = simulatedRun();
    rerunRun.duration_s = 900;
    pending.resolve(rerunRun);

    expect(await rerunLoad).toBe(true);
    expect(usePlaybackStore.getState().data?.duration_s).toBe(900);
  });

  it("resolves false and keeps the shown run when a rerun fails", async () => {
    const store = usePlaybackStore.getState();
    await store.loadConnectionRun(MCGILL, async () => simulatedRun());
    const shown = usePlaybackStore.getState().data;
    const failing = async (): Promise<StationViewData> => {
      throw new Error("The simulation run failed on the server (HTTP 500). Try again in a moment.");
    };

    expect(await store.loadConnectionRun(MCGILL, failing, undefined, { rerun: true })).toBe(false);
    expect(usePlaybackStore.getState().data).toBe(shown);
    expect(usePlaybackStore.getState().runStatus).toBe("error");
    expect(usePlaybackStore.getState().runError).toContain("HTTP 500");
  });
});
