// AI contribution: 50% or more AI-generated
/**
 * Run settings chosen in the panel, kept apart from playback state.
 *
 * `draft` is what the controls show and edit. Nothing is sent until the user
 * clicks "Run scenario"; `applied` then records the settings that produced the
 * run now shown for each connection, so the results can be labelled with the
 * strategy and limits that made them even after the draft changes again.
 */
import { create } from "zustand";

import { DEFAULT_RUN_SETTINGS, applyRunSettings } from "../lib/run-settings";
import type { RunSettings } from "../types/runSettings";

interface RunSettingsStore {
  // Values currently shown by the controls; always within the API's ranges.
  draft: RunSettings;
  // Settings behind the displayed run, keyed by connection ID.
  applied: Readonly<Record<string, RunSettings>>;
  // Change one or more controls; numbers are clamped and snapped to their step.
  update: (patch: Partial<RunSettings>) => void;
  // Put every control back to the backend defaults without running anything.
  reset: () => void;
  // Remember which settings produced the run just loaded for a connection.
  markApplied: (connectionId: string, settings: RunSettings) => void;
}

export const useRunSettingsStore = create<RunSettingsStore>((set) => ({
  draft: DEFAULT_RUN_SETTINGS,
  applied: {},

  update: (patch) => set((state) => ({ draft: applyRunSettings(state.draft, patch) })),

  reset: () => set({ draft: DEFAULT_RUN_SETTINGS }),

  // A copy is stored so later edits to the draft cannot change the label.
  markApplied: (connectionId, settings) =>
    set((state) => ({ applied: { ...state.applied, [connectionId]: { ...settings } } })),
}));
