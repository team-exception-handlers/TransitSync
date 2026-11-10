// AI contribution: 50% or more AI-generated
/**
 * Authoritative frontend playback position, loaded run and connection selection.
 *
 * Selecting a connection shows its catalog run at once (a mock until the
 * simulator output arrives) and restarts playback; `loadConnectionRun` then
 * replaces that entry with the API's run output for the same connection.
 */
import { create } from "zustand";

import { getNetworkSnapshot } from "../lib/getNetworkSnapshot";
import type { ConnectionRunLoader } from "../lib/simulation-api";
import { parseStationViewData } from "../lib/validateStationView";

import type { NetworkSnapshot, StationViewData } from "../types/stationView";
import { PLAYBACK_SPEEDS, type PlaybackSpeed } from "../types/playback-speed";

/**
 * Where the shown run came from: the bundled mock catalog, an API request in
 * flight, the simulator's run output, or a failed request (mock still shown).
 */
export type RunStatus = "mock" | "loading" | "simulated" | "error";

interface StationViewStore {
  data: StationViewData | null;
  availableRuns: StationViewData[];
  setAvailableRuns: (runs: readonly unknown[]) => void;

  // Connections whose catalog entry has been replaced by simulator output.
  simulatedConnectionIds: readonly string[];
  runStatus: RunStatus;
  // User-facing reason for the last failed load; null unless status is "error".
  runError: string | null;
  // Fetch the selected connection's run output and show it from time 0.
  // `rerun` replaces output already loaded (new run settings) instead of
  // reusing it. Resolves true only when the fetched run is now shown.
  loadConnectionRun: (
    connectionId: string,
    loader: ConnectionRunLoader,
    signal?: AbortSignal,
    options?: { rerun?: boolean },
  ) => Promise<boolean>;

  // current position in the run, in seconds
  currentTime_s: number;
  selectedConnectionId: string | null;
  isPlaying: boolean;
  speed: PlaybackSpeed;
  setSpeed: (speed: number) => void;
  // Monotonic wall time, in milliseconds; null while paused.
  updatedAt_ms: number | null;
  // Simulation position at that wall-time anchor, not an independent UI clock.
  anchorTime_s: number;
  play: () => void;
  pause: () => void;
  rewind30: () => void;
  advance: () => void;

  // load simulation data
  loadData: (data: unknown) => void;

  // seek to an arbitrary timestamp
  seek: (time_s: number) => void;

  // update shared connection state
  selectConnection: (connectionId: string) => void;

  // return network state at the current timestamp
  snapshot: () => NetworkSnapshot | null;

  // return network state at any requested timestamp
  // without changing the current playback position
  getSnapshotAt: (
    time_s: number
  ) => NetworkSnapshot | null;
}

// make sure the requested time is within the run.
 
function clampTime(
  time_s: number,
  duration_s: number
): number {
  if (!Number.isFinite(time_s)) {
    return 0;
  }

  return Math.max(
    0,
    Math.min(time_s, duration_s)
  );
}

// A different run has a different timeline, so any run change restarts paused
// at 0 s; speed is a viewer preference and survives the change.
const PLAYBACK_RESET = {
  currentTime_s: 0,
  isPlaying: false,
  updatedAt_ms: null,
  anchorTime_s: 0,
} as const;

// Number of the most recent run load that got past the reuse check. Only that
// load may publish: two reruns of the same connection both pass the selection
// check, so without this an older request finishing last would overwrite the
// newer results. Kept outside the store state because no component renders it.
let latestLoad = 0;

/**
 * Swap the catalog entry (or entries) sharing a connection with `run` for `run`.
 *
 * The new run takes the position of the first entry it replaces, so the
 * selector keeps its order; removing every overlapping entry keeps connection
 * IDs unique even when a run bundles several connections.
 */
function replaceRun(runs: readonly StationViewData[], run: StationViewData): StationViewData[] {
  const ids = new Set(run.connections.map((connection) => connection.id));
  const overlaps = (item: StationViewData) =>
    item.connections.some((connection) => ids.has(connection.id));
  const index = runs.findIndex(overlaps);
  const kept = runs.filter((item) => !overlaps(item));
  if (index === -1) return [...kept, run];
  // Entries before the first overlap are never removed, so index stays valid.
  return [...kept.slice(0, index), run, ...kept.slice(index)];
}

/** Convert elapsed wall milliseconds into run seconds, clamped at the run end. */
function positionNow(state: StationViewStore, now_ms: number): number {
  if (!state.isPlaying || state.updatedAt_ms === null) return state.currentTime_s;
  const elapsed_s = Math.max(0, now_ms - state.updatedAt_ms) / 1000;
  return clampTime(state.anchorTime_s + elapsed_s * state.speed, state.data?.duration_s ?? 0);
}

export const usePlaybackStore = create<StationViewStore>(
  (set, get) => ({
    // INITIAL STATE
    data: null,
    availableRuns: [],
    currentTime_s: 0,
    selectedConnectionId: null,
    isPlaying: false,
    speed: 1,
    updatedAt_ms: null,
    anchorTime_s: 0,
    simulatedConnectionIds: [],
    runStatus: "mock",
    runError: null,

    // Validate the entire catalog before publishing it, so failure is atomic.
    // A new catalog holds no simulator output yet.
    setAvailableRuns: (runs) => {
      const availableRuns = runs.map(parseStationViewData);
      const ids = availableRuns.flatMap((run) => run.connections.map((item) => item.id));
      if (new Set(ids).size !== ids.length) throw new Error("Duplicate connection in catalog");
      set({ availableRuns, simulatedConnectionIds: [] });
    },

    // Only the latest selection may publish: a response for a connection the
    // user has since left, or for an aborted request, is dropped silently.
    loadConnectionRun: async (connectionId, loader, signal, options) => {
      const isSelected = () => !signal?.aborted && get().selectedConnectionId === connectionId;
      // Output already loaded for this connection is reused, unless the caller
      // asks for a fresh run with different settings.
      const reuse = !options?.rerun && get().simulatedConnectionIds.includes(connectionId);
      if (!isSelected() || reuse) return false;
      // Numbered only once it will really load, so a reused call never
      // cancels a rerun that is still in flight.
      const load = ++latestLoad;
      const isCurrent = () => load === latestLoad && isSelected();
      set({ runStatus: "loading", runError: null });
      try {
        const run = await loader(connectionId, signal);
        if (!isCurrent()) return false;
        const state = get();
        const runIds = run.connections.map((connection) => connection.id);
        set({
          ...PLAYBACK_RESET,
          data: run,
          availableRuns: replaceRun(state.availableRuns, run),
          simulatedConnectionIds: [...new Set([...state.simulatedConnectionIds, ...runIds])],
          runStatus: "simulated",
        });
        return true;
      } catch (error) {
        if (!isCurrent()) return false;
        // Keep the run on screen and its playback position; only report the failure.
        const reason = error instanceof Error ? error.message : String(error);
        set({ runStatus: "error", runError: reason });
        return false;
      }
    },

    loadData: (value) => {
      const data = parseStationViewData(value);

      set({
        data,
        currentTime_s: 0,
        isPlaying: false,
        speed: 1,
        updatedAt_ms: null,
        anchorTime_s: 0,
        selectedConnectionId:
          data.connections[0]?.id ?? null,
      });
    },

    // seeking
    seek: (time_s) => {
      set((state) => {
        const duration = state.data?.duration_s ?? 0;
        const currentTime_s = clampTime(time_s, duration);
        const isPlaying = state.isPlaying && currentTime_s < duration;
        return { currentTime_s, anchorTime_s: currentTime_s, isPlaying,
          updatedAt_ms: isPlaying ? performance.now() : null };
      });
    },

    // Repeated Play is a no-op, including its wall-time anchor.
    play: () => {
      const state = get();
      if (state.isPlaying || !state.data || state.currentTime_s >= state.data.duration_s) return;
      set({ isPlaying: true, anchorTime_s: state.currentTime_s, updatedAt_ms: performance.now() });
    },

    // Settle the fraction since the last frame before freezing the display.
    pause: () => {
      const state = get();
      if (!state.isPlaying) return;
      set({ currentTime_s: positionNow(state, performance.now()), isPlaying: false, updatedAt_ms: null });
    },

    // Figma/wiki define rewind as 30 simulated seconds, independent of speed.
    // Settle the in-flight fraction first; preserve running/paused intent.
    rewind30: () => {
      const state = get();
      if (!state.data) return;
      const now = performance.now();
      const currentTime_s = Math.max(0, positionNow(state, now) - 30);
      set({ currentTime_s, anchorTime_s: currentTime_s,
        updatedAt_ms: state.isPlaying ? now : null });
    },

    // Settle at the OLD rate before selecting the NEW rate, even between frames.
    setSpeed: (speed) => {
      if (!PLAYBACK_SPEEDS.some((allowed) => allowed === speed)) {
        throw new Error(`Unsupported playback speed: ${speed}`);
      }
      const state = get();
      if (state.speed === speed) return;
      const now = performance.now();
      const currentTime_s = positionNow(state, now);
      const isPlaying = state.isPlaying && currentTime_s < (state.data?.duration_s ?? 0);
      set({ speed: speed as PlaybackSpeed, currentTime_s, anchorTime_s: currentTime_s, isPlaying,
        updatedAt_ms: isPlaying ? now : null });
    },

    // A frame only moves the presentation clock; recorded results stay immutable.
    advance: () => {
      const state = get();
      if (!state.isPlaying || !state.data) return;
      const now = performance.now();
      const currentTime_s = positionNow(state, now);
      const isPlaying = currentTime_s < state.data.duration_s;
      // Keep a fixed origin between user actions: frame frequency and dropped
      // frames must not accumulate rounding drift or change the playback rate.
      set({ currentTime_s, isPlaying, updatedAt_ms: isPlaying ? state.updatedAt_ms : null });
    },

    selectConnection: (connectionId) => {
      const state = get();
      if (connectionId === state.selectedConnectionId) return;
      const data = state.availableRuns.find((run) =>
        run.connections.some((connection) => connection.id === connectionId)
      ) ?? state.data;

      if (
        !data?.connections.some(
          (connection) =>
            connection.id === connectionId
        )
      ) {
        throw new Error(
          `Unknown connection: ${connectionId}`
        );
      }

      set({
        ...PLAYBACK_RESET,
        data,
        selectedConnectionId: connectionId,
        // The status describes the run now shown, not the previous selection.
        runStatus: state.simulatedConnectionIds.includes(connectionId) ? "simulated" : "mock",
        runError: null,
      });
    },

    snapshot: () => {
      const {
        data,
        currentTime_s
      } = get();

      if (!data) {
        return null;
      }

      return getNetworkSnapshot(
        data,
        currentTime_s
      );
    },

    getSnapshotAt: (time_s) => {
      const { data } = get();
      if (!data) {
        return null;
      }

      return getNetworkSnapshot(
        data,
        time_s
      );
    },

  })
);
