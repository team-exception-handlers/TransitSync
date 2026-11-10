// AI contribution: 50% or more AI-generated
/**
 * Shows which run settings produced the simulator output on screen (#45, #50),
 * next to the station heading. Hidden for mock playback, which has no settings.
 */
import { DEFAULT_RUN_SETTINGS, formatSeconds, formatThreshold, strategyLabel } from "../lib/run-settings";
import { usePlaybackStore } from "../store/usePlaybackStore";
import { useRunSettingsStore } from "../store/useRunSettingsStore";

/** A short definition list: strategy, maximum hold and, for Adaptive, the threshold. */
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
      <div>
        <dt>Strategy</dt>
        <dd>{strategyLabel(settings.strategy)}</dd>
      </div>
      <div>
        <dt>Max hold</dt>
        <dd>{formatSeconds(settings.max_hold_time)}</dd>
      </div>
      {settings.strategy === "adaptive" && (
        <div>
          <dt>Irregularity threshold</dt>
          <dd>{formatThreshold(settings.irregularity_threshold)}</dd>
        </div>
      )}
    </dl>
  );
}
