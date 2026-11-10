// AI contribution: 50% or more AI-generated
/**
 * Adaptive mode switches for the playback timeline (#60).
 *
 * The Adaptive strategy writes one decision-audit record of kind
 * "mode_switch" each time it changes between connection protection and
 * headway regulation (simulator/control/decision_audit.py). This module picks
 * those records out of a run's `decisions` list and places them on the
 * timeline. It reads the list defensively because the list is not part of the
 * validated station-view contract: records of other kinds, or malformed ones,
 * are skipped instead of breaking playback.
 */

/** `kind` of a mode-switch record; mirrors KIND_MODE_SWITCH in the simulator. */
export const KIND_MODE_SWITCH = "mode_switch";

/** One switch, positioned on the timeline. */
export interface ModeSwitchMarker {
  /** Stable React key: switches on different platforms can share a time. */
  id: string;
  /** Seconds from the start of the run. */
  time_s: number;
  /** Position along the timeline, from 0 (start) to 1 (end of the run). */
  fraction: number;
  from_mode: string;
  to_mode: string;
}

/** "headway_regulation" reads as "headway regulation" in labels. */
export function modeLabel(mode: string): string {
  return mode.replaceAll("_", " ");
}

/** Read one audit record; null unless it is a usable mode switch inside the run. */
function toMarker(record: unknown, duration_s: number): ModeSwitchMarker | null {
  if (typeof record !== "object" || record === null) return null;
  const { kind, time_s, from_mode, to_mode, platform_id } = record as Record<string, unknown>;
  if (kind !== KIND_MODE_SWITCH) return null;
  if (typeof time_s !== "number" || !Number.isFinite(time_s)) return null;
  if (typeof from_mode !== "string" || typeof to_mode !== "string") return null;
  // A switch outside the run cannot be placed on its timeline.
  if (time_s < 0 || time_s > duration_s) return null;
  return {
    id: `${time_s}:${String(platform_id)}:${to_mode}`,
    time_s,
    fraction: time_s / duration_s,
    from_mode,
    to_mode,
  };
}

/**
 * Mode-switch markers of a run, in time order. Returns an empty list when the
 * run has no duration, no `decisions` list or no mode-switch records, which is
 * the case for every strategy except Adaptive.
 */
export function modeSwitchMarkers(run: unknown): ModeSwitchMarker[] {
  if (typeof run !== "object" || run === null) return [];
  const { decisions, duration_s } = run as { decisions?: unknown; duration_s?: unknown };
  if (!Array.isArray(decisions) || typeof duration_s !== "number" || duration_s <= 0) return [];
  const markers = decisions.flatMap((record: unknown) => {
    const marker = toMarker(record, duration_s);
    return marker === null ? [] : [marker];
  });
  return markers.toSorted((a, b) => a.time_s - b.time_s);
}
