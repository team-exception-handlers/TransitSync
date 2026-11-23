// AI contribution: 50% or more AI-generated
/**
 * Which workspace screen the sidebar shows (#408).
 *
 * The app has no router: the five Release 2 screens are a single piece of UI
 * state, so a Zustand store is enough and keeps the current view next to the
 * other front-end stores. Playback, the loaded run and the selected
 * connection stay in `usePlaybackStore`, so switching views never resets them.
 */
import { create } from "zustand";

/** One sidebar screen; the order of `VIEWS` below is the order shown. */
export type AppView = "station" | "compare" | "results" | "setup" | "sources";

/**
 * Lookup table the sidebar renders from, so adding a screen is one new row
 * here plus its entry in the view table in `App.tsx`.
 */
export const VIEWS: readonly { id: AppView; label: string }[] = [
  { id: "station", label: "Station view" },
  { id: "compare", label: "Compare" },
  { id: "results", label: "Results" },
  { id: "setup", label: "Scenario setup" },
  { id: "sources", label: "Sources" },
];

interface ViewStore {
  // Screen currently shown in the main content area.
  activeView: AppView;
  // Show another screen; the other stores are left untouched.
  setView: (view: AppView) => void;
}

export const useViewStore = create<ViewStore>((set) => ({
  activeView: "station",
  setView: (view) => set({ activeView: view }),
}));
