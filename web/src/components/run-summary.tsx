// AI contribution: 50% or more AI-generated
/**
 * Shows which run settings produced the simulator output on screen (#45, #50,
 * #183, #182), next to the station heading. Hidden for mock playback, which
 * has no settings.
 */
import {
  DEFAULT_DISRUPTION_MAGNITUDES,
  DEFAULT_RUN_SETTINGS,
  formatErrorMagnitude,
  formatHeadwayIrregularity,
  formatSeconds,
  formatThreshold,
  strategyLabel,
} from "../lib/run-settings";
import { usePlaybackStore } from "../store/usePlaybackStore";
import { useRunSettingsStore } from "../store/useRunSettingsStore";
import type { RunSettings } from "../types/runSettings";

const DISRUPTION_LABELS: Record<RunSettings["disruption_preset"], string> = {
  none: "None",
  platform_delay: "Platform delay",
  line_suspension: "Line suspension",
  uneven_headways: "Uneven headways",
};

/** Format the selected disruption magnitude with its correct unit. */
function disruptionMagnitudeRow(
  preset: Exclude<RunSettings["disruption_preset"], "none" | undefined>,
  magnitude: number | undefined,
): [string, string] {
  if (preset === "uneven_headways") {
    return [
      "Headway irregularity",
      formatHeadwayIrregularity(
        magnitude ?? DEFAULT_DISRUPTION_MAGNITUDES.uneven_headways,
      ),
    ];
  }
  if (preset === "line_suspension") {
    return ["Suspension duration", formatSeconds(magnitude ?? 60)];
  }
  return ["Disruption magnitude", formatSeconds(magnitude ?? 60)];
}

/**
 * Label and display text for each setting, in reading order. The threshold
 * is listed only for Adaptive, the one strategy that uses it.
 */
function summaryRows(settings: RunSettings): [label: string, text: string][] {
  const disruptionPreset = settings.disruption_preset ?? "none";
  const rows: [string, string][] = [
    ["Strategy", strategyLabel(settings.strategy)],
    ["Max hold", formatSeconds(settings.max_hold_time)],
  ];
  if (settings.strategy === "adaptive") {
    rows.push(["Irregularity threshold", formatThreshold(settings.irregularity_threshold)]);
  }
  rows.push(
    ["Error magnitude", formatErrorMagnitude(settings.error_magnitude)],
    ["Passenger flow", settings.passenger_flow],
    ["Disruption", DISRUPTION_LABELS[disruptionPreset]],
  );
  if (disruptionPreset !== "none") {
    rows.push(["Disruption start", formatSeconds(settings.disruption_time_s ?? 120)]);
    rows.push(disruptionMagnitudeRow(disruptionPreset, settings.disruption_magnitude));
  }
  return rows;
}

/** A short definition list of the settings behind the displayed run. */
export function RunSummary() {
  const connectionId = usePlaybackStore((state) => state.selectedConnectionId);
  const isSimulated = usePlaybackStore((state) =>
    connectionId !== null && state.simulatedConnectionIds.includes(connectionId));
  const applied = useRunSettingsStore((state) =>
    connectionId === null ? undefined : state.applied[connectionId]);
  // Mock runs were not produced by any settings, so there is nothing to label.
  if (!isSimulated) return null;

  // A run loaded by selecting a connection sends no settings, so the API used
  // its defaults; those equal the panel's defaults.
  const settings = applied ?? DEFAULT_RUN_SETTINGS;

  return (
    <dl className="run-summary" aria-label="Settings used for this run">
      {summaryRows(settings).map(([label, text]) => (
        <div key={label}>
          <dt>{label}</dt>
          <dd>{text}</dd>
        </div>
      ))}
    </dl>
  );
}
