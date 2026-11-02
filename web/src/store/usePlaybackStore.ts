// AI contribution: 50% or more AI-generated

import { create } from "zustand";

import { getNetworkSnapshot } from "../lib/getNetworkSnapshot";
import { parseStationViewData } from "../lib/validateStationView";

import type {
    NetworkSnapshot,
    StationViewData,
} from "../types/stationView";

interface StationViewStore {
    // Loaded simulation data.
    data: StationViewData | null;

    // Simulation time in seconds.
    currentTime_s: number;

    // Connection ID stored for future UI integration.
    selectedConnectionId: string | null;

    // Load and validate simulation data.
    loadData: (data: unknown) => void;

    // Update the current simulation timestamp.
    seek: (time_s: number) => void;

    // Update shared selection state.
    selectConnection: (connectionId: string) => void;

    // Compute the network state at the current timestamp.
    snapshot: () => NetworkSnapshot | null;
}

/**
 * Restrict a requested timestamp to the simulation duration.
 */
function clampTime(
    time_s: number,
    duration_s: number,
): number {
    if (!Number.isFinite(time_s)) {
        return 0;
    }

    return Math.max(
        0,
        Math.min(time_s, duration_s),
    );
}

export const usePlaybackStore = create<StationViewStore>(
    (set, get) => ({
        // Initial state.
        data: null,

        currentTime_s: 0,

        selectedConnectionId: null,

        /**
         * Load a station-view dataset.
         *
         * The validation function ensures that the input
         * conforms to the station-view data contract.
         */
        loadData: (value) => {
            const data = parseStationViewData(value);

            set({
                data,

                // Initial mock timestamp
                currentTime_s: Math.min(
                    138,
                    data.duration_s,
                ),

                selectedConnectionId:
                    data.connections[0]?.id ?? null,
            });
        },

        seek: (time_s) => {
            set((state) => ({
                currentTime_s: clampTime(
                    time_s,
                    state.data?.duration_s ?? 0,
                ),
            }));
        },

        selectConnection: (connectionId) => {
            const data = get().data;

            if (
                !data?.connections.some(
                    (connection) =>
                        connection.id === connectionId,
                )
            ) {
                throw new Error(
                    `Unknown connection: ${connectionId}`,
                );
            }

            set({
                selectedConnectionId: connectionId,
            });
        },

        snapshot: () => {
            const {
                data,
                currentTime_s,
            } = get();

            if (!data) {
                return null;
            }

            return getNetworkSnapshot(
                data,
                currentTime_s,
            );
        },
    }),
);