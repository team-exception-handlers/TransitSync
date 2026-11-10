// AI contribution: 50% or more AI-generated
/**
 * Adaptive mode switches for the playback timeline (#60).
 *
 * The Adaptive strategy changes between connection protection and headway
 * regulation as service gets more or less regular. The run endpoint returns
 * those changes for the selected connection's platforms in `mode_switches`
 * (ModeSwitchResponse in api/station_view.py); this module places them on
 * the timeline. It reads the list defensively because it is not part of the
 * validated station-view contract: a malformed record is skipped instead of
 * breaking playback, and an older API without the key gives no markers.
 */

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

/** Read one record; null unless it is a usable mode switch inside the run. */
function toMarker(record: unknown, duration_s: number): ModeSwitchMarker | null {
  if (typeof record !== "object" || record === null) return null;
  const { time_s, from_mode, to_mode, platform_id } = record as Record<string, unknown>;
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
 * run has no duration or no `mode_switches` list, or the list is empty, which
 * is the case for every strategy except Adaptive and for the mock runs.
 */
export function modeSwitchMarkers(run: unknown): ModeSwitchMarker[] {
  if (typeof run !== "object" || run === null) return [];
  const { mode_switches, duration_s } = run as { mode_switches?: unknown; duration_s?: unknown };
  if (!Array.isArray(mode_switches) || typeof duration_s !== "number" || duration_s <= 0) {
    return [];
  }
  const markers = mode_switches.flatMap((record: unknown) => {
    const marker = toMarker(record, duration_s);
    return marker === null ? [] : [marker];
  });
  return markers.toSorted((a, b) => a.time_s - b.time_s);
}
