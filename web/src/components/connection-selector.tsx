// AI contribution: 50% or more AI-generated
/**
 * Figma connection segments backed by the shared validated run catalog.
 * Availability and selection come from Zustand; no component state can drift
 * away from the run shown on the Canvas or its playback position.
 *
 * The backend's connection list (#76) is authoritative when the store has
 * one: it lists every connection with its own metro line directly, instead
 * of deriving the line from a loaded run's platforms. Without one (no API
 * configured, or the request failed) the run catalog's own connections and
 * platforms are the offline fallback, unchanged from before #76.
 */
import { usePlaybackStore } from "../store/usePlaybackStore";

interface ConnectionChoice {
  id: string;
  label: string;
  // Undefined only in the fallback path, if a run's platforms do not
  // contain the connection's metro-side platform.
  metroLineId: string | undefined;
}

function connectionChoicesFromCatalog(
  availableConnections: ReturnType<typeof usePlaybackStore.getState>["availableConnections"],
): ConnectionChoice[] {
  return (availableConnections ?? []).map((connection) => ({
    id: connection.id,
    label: connection.label,
    metroLineId: connection.metro_line_id,
  }));
}

function connectionChoicesFromRuns(
  availableRuns: ReturnType<typeof usePlaybackStore.getState>["availableRuns"],
  data: ReturnType<typeof usePlaybackStore.getState>["data"],
): ConnectionChoice[] {
  // A directly loaded run still works when no catalog has been registered.
  let runs = availableRuns;
  if (runs.length === 0 && data) runs = [data];
  return runs.flatMap((run) => run.connections.map((connection) => {
    const metro = run.platforms.find((item) => item.platform_id === connection.to_platform_id);
    return { id: connection.id, label: connection.label, metroLineId: metro?.line_id };
  }));
}

/** Native buttons support Tab, Enter and Space without a second selection state. */
export function ConnectionSelector() {
  const availableConnections = usePlaybackStore((state) => state.availableConnections);
  const availableRuns = usePlaybackStore((state) => state.availableRuns);
  const data = usePlaybackStore((state) => state.data);
  const selected = usePlaybackStore((state) => state.selectedConnectionId);
  const select = usePlaybackStore((state) => state.selectConnection);
  const choices = availableConnections !== null
    ? connectionChoicesFromCatalog(availableConnections)
    : connectionChoicesFromRuns(availableRuns, data);

  return (
    <fieldset className="connection-selector segmented-control" aria-label="Station connection">
      {choices.map((connection) => {
        const isSelected = selected === connection.id;
        return (
          <button key={connection.id} type="button"
            className="connection-option"
            aria-pressed={isSelected}
            onClick={() => select(connection.id)}>
            {/* A checkmark glyph plus bold text mark selection; colour is not the only cue. */}
            <span className="selected-mark" aria-hidden="true">{isSelected ? "✓" : ""}</span>
            <span className="line-swatch rem" aria-hidden="true" />
            <span className={`line-swatch ${connection.metroLineId}`} aria-hidden="true" />
            {connection.label}
            <span className="connection-line">{connection.metroLineId} line</span>
          </button>
        );
      })}
    </fieldset>
  );
}
