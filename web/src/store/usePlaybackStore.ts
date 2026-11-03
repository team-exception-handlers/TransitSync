// AI contribution: 50% or more AI-generated
/** Authoritative frontend playback position, loaded run and connection selection. */
import { create } from "zustand";

import { getNetworkSnapshot } from "../lib/getNetworkSnapshot";
import { parseStationViewData } from "../lib/validateStationView";

import type { NetworkSnapshot, StationViewData } from "../types/stationView";

interface StationViewStore {
  data: StationViewData | null;
  availableRuns: StationViewData[];
  setAvailableRuns: (runs: readonly unknown[]) => void;

  // current position in the run, in seconds
  currentTime_s: number;
  selectedConnectionId: string | null;
  isPlaying: boolean;
  // Monotonic wall time, in milliseconds; null while paused.
  updatedAt_ms: number | null;
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

/** Convert elapsed wall milliseconds into run seconds, clamped at the run end. */
function positionNow(state: StationViewStore, now_ms: number): number {
  if (!state.isPlaying || state.updatedAt_ms === null) return state.currentTime_s;
  const elapsed_s = Math.max(0, now_ms - state.updatedAt_ms) / 1000;
  return clampTime(state.currentTime_s + elapsed_s, state.data?.duration_s ?? 0);
}

export const usePlaybackStore = create<StationViewStore>(
  (set, get) => ({
    // INITIAL STATE
    data: null,
    availableRuns: [],
    currentTime_s: 0,
    selectedConnectionId: null,
    isPlaying: false,
    updatedAt_ms: null,

    // Validate the entire catalog before publishing it, so failure is atomic.
    setAvailableRuns: (runs) => {
      const availableRuns = runs.map(parseStationViewData);
      const ids = availableRuns.flatMap((run) => run.connections.map((item) => item.id));
      if (new Set(ids).size !== ids.length) throw new Error("Duplicate connection in catalog");
      set({ availableRuns });
    },

    loadData: (value) => {
      const data = parseStationViewData(value);

      set({
        data,
        currentTime_s: 0,
        isPlaying: false,
        updatedAt_ms: null,
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
        return { currentTime_s, isPlaying, updatedAt_ms: isPlaying ? performance.now() : null };
      });
    },

    // Repeated Play is a no-op, including its wall-time anchor.
    play: () => {
      const state = get();
      if (state.isPlaying || !state.data || state.currentTime_s >= state.data.duration_s) return;
      set({ isPlaying: true, updatedAt_ms: performance.now() });
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
      set({ currentTime_s: Math.max(0, positionNow(state, now) - 30),
        updatedAt_ms: state.isPlaying ? now : null });
    },

    // A frame only moves the presentation clock; recorded results stay immutable.
    advance: () => {
      const state = get();
      if (!state.isPlaying || !state.data) return;
      const now = performance.now();
      const currentTime_s = positionNow(state, now);
      const isPlaying = currentTime_s < state.data.duration_s;
      set({ currentTime_s, isPlaying, updatedAt_ms: isPlaying ? now : null });
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
        data,
        currentTime_s: 0,
        isPlaying: false,
        updatedAt_ms: null,
        selectedConnectionId: connectionId,
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
