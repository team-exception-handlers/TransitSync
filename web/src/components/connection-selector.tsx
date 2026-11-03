// AI contribution: 50% or more AI-generated
/**
 * Figma connection segments backed by the shared validated run catalog.
 * Availability and selection come from Zustand; no component state can drift
 * away from the run shown on the Canvas or its playback position.
 */
import { usePlaybackStore } from "../store/usePlaybackStore";

/** Native buttons support Tab, Enter and Space without a second selection state. */
export function ConnectionSelector() {
  const availableRuns = usePlaybackStore((state) => state.availableRuns);
  const data = usePlaybackStore((state) => state.data);
  const selected = usePlaybackStore((state) => state.selectedConnectionId);
  const select = usePlaybackStore((state) => state.selectConnection);
  // A directly loaded run still works when no catalog has been registered.
  let runs = availableRuns;
  if (runs.length === 0 && data) runs = [data];

  return (
    <div className="connection-selector segmented-control" role="group" aria-label="Station connection">
      {runs.flatMap((run) => run.connections.map((connection) => {
        const metro = run.platforms.find((item) => item.platform_id === connection.to_platform_id);
        return (
          <button key={connection.id} type="button"
            aria-pressed={selected === connection.id}
            onClick={() => select(connection.id)}>
            {/* Names and line text preserve meaning without relying on color. */}
            <span className="line-swatch rem" aria-hidden="true" />
            <span className={`line-swatch ${metro?.line_id}`} aria-hidden="true" />
            {connection.label}
            <span className="connection-line">{metro?.line_id} line</span>
          </button>
        );
      }))}
    </div>
  );
}
