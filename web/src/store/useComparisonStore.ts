// AI contribution: 50% or more AI-generated
/**
 * The holding and no-holding runs shown side by side on the Compare screen
 * (US-4.1, #230).
 *
 * This store only holds the loaded pair and its loading status. It has no
 * playback state: both panels read the time from `usePlaybackStore`, so one
 * clock (Observer pattern) drives both and they can never drift apart.
 */
import { create } from "zustand";

import { buildRunRequest } from "../lib/run-settings";
import type { ComparisonRunner, PassengerSplit, StartingConditions } from "../lib/simulation-api";
import type { StationViewData } from "../types/stationView";
import type { RunSettings } from "../types/runSettings";

/** Nothing requested yet, a request in flight, a pair shown, or the last request failed. */
export type ComparisonStatus = "idle" | "loading" | "ready" | "error";

interface ComparisonStore {
  // Connection and request body behind the pair now shown; null before the first load.
  connectionId: string | null;
  settingsKey: string | null;
  holding: StationViewData | null;
  noHolding: StationViewData | null;
  holdingStrategy: string | null;
  startingConditions: StartingConditions | null;
  // Who holding helped or harmed in this pair (#285); null before the first load.
  passengerSplit: PassengerSplit | null;
  status: ComparisonStatus;
  // User-facing reason for the last failure; null unless status is "error".
  error: string | null;
  // Fetch both runs for these settings. Resolves true only when a new pair is
  // now shown; a pair already loaded for the same request is reused.
  loadComparison: (
    connectionId: string,
    settings: RunSettings,
    runner: ComparisonRunner,
    signal?: AbortSignal,
  ) => Promise<boolean>;
}

/** Empty state, also used by tests to reset the store between cases. */
export const EMPTY_COMPARISON = {
  connectionId: null,
  settingsKey: null,
  holding: null,
  noHolding: null,
  holdingStrategy: null,
  startingConditions: null,
  passengerSplit: null,
  status: "idle",
  error: null,
} as const satisfies Omit<ComparisonStore, "loadComparison">;

// Numbers every load that really starts, so only the newest one may publish.
let latestLoad = 0;

export const useComparisonStore = create<ComparisonStore>((set, get) => ({
  ...EMPTY_COMPARISON,

  loadComparison: async (connectionId, settings, runner, signal) => {
    // The request body is the key: two settings objects that send the same
    // body give the same runs, so the pair on screen can be reused.
    const settingsKey = JSON.stringify(buildRunRequest(connectionId, settings));
    if (signal?.aborted) return false;
    const loaded = get();
    if (loaded.holding !== null && loaded.settingsKey === settingsKey) {
      // The pair on screen is the one asked for. A load for other settings
      // may have been abandoned or failed meanwhile, so drop anything still
      // in flight and clear its "loading" or "error" status.
      latestLoad += 1;
      if (loaded.status !== "ready") set({ status: "ready", error: null });
      return false;
    }
    const load = ++latestLoad;
    // An aborted request (the user left the screen or changed connection) and
    // a request overtaken by a newer one are both dropped without a trace.
    const isCurrent = () => load === latestLoad && !signal?.aborted;
    // An aborted load that no newer one replaced must not leave the status at
    // "loading". It falls back to "ready" only when the pair in the store is
    // for this connection; a pair for another connection is hidden on screen,
    // so "ready" would describe runs the user cannot see.
    const dropLoad = () => {
      if (load !== latestLoad) return false;
      const shown = get();
      const pairIsForThisConnection = shown.holding !== null && shown.connectionId === connectionId;
      set({ status: pairIsForThisConnection ? "ready" : "idle" });
      return false;
    };
    set({ status: "loading", error: null });
    try {
      const pair = await runner(connectionId, settings, signal);
      if (!isCurrent()) return dropLoad();
      set({
        connectionId,
        settingsKey,
        holding: pair.holding,
        noHolding: pair.noHolding,
        holdingStrategy: pair.holdingStrategy,
        startingConditions: pair.startingConditions,
        passengerSplit: pair.passengerSplit,
        status: "ready",
      });
      return true;
    } catch (error) {
      if (!isCurrent()) return dropLoad();
      // The previous pair stays on screen; only the failure is reported.
      const reason = error instanceof Error ? error.message : String(error);
      set({ status: "error", error: reason });
      return false;
    }
  },
}));
