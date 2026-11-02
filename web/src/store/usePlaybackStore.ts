import { create } from "zustand";

import { getNetworkSnapshot } from "../lib/getNetworkSnapshot";
import { parseStationViewData } from "../lib/validateStationView";

import type { NetworkSnapshot, StationViewData } from "../types/stationView";

interface StationViewStore {
  data: StationViewData | null;

  // current position in the run, in seconds
  currentTime_s: number;
  selectedConnectionId: string | null;

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

export const usePlaybackStore = create<StationViewStore>(
  (set, get) => ({
    // INITIAL STATE
    data: null,
    currentTime_s: 0,
    selectedConnectionId: null,

    loadData: (value) => {
      const data = parseStationViewData(value);

      set({
        data,
        currentTime_s: 0,
        selectedConnectionId:
          data.connections[0]?.id ?? null,
      });
    },

    // seeking
    seek: (time_s) => {
      set((state) => ({
        currentTime_s: clampTime(
          time_s,
          state.data?.duration_s ?? 0
        ),
      }));
    },

    selectConnection: (connectionId) => {
      const data = get().data;

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