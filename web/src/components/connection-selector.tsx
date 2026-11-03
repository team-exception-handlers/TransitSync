// AI contribution: 50% or more AI-generated
/** Figma connection segments backed by the shared validated run catalog. */
import { usePlaybackStore } from "../store/usePlaybackStore";

/** Native buttons support Tab, Enter and Space without a second selection state. */
export function ConnectionSelector() {
  const availableRuns = usePlaybackStore((state) => state.availableRuns);
  const data = usePlaybackStore((state) => state.data);
  const selected = usePlaybackStore((state) => state.selectedConnectionId);
  const select = usePlaybackStore((state) => state.selectConnection);
  const runs = availableRuns.length ? availableRuns : data ? [data] : [];

  return (
    <div className="connection-selector segmented-control" role="group" aria-label="Station connection">
      {runs.flatMap((run) => run.connections.map((connection) => {
        const metro = run.platforms.find((item) => item.platform_id === connection.to_platform_id);
        return (
          <button key={connection.id} type="button"
            aria-pressed={selected === connection.id}
            onClick={() => select(connection.id)}>
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
