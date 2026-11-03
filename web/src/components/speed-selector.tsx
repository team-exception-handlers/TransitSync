// AI contribution: 50% or more AI-generated
/** Figma speed segments use the store's single supported-speed contract. */
import { PLAYBACK_SPEEDS } from "../types/playback-speed";
import { usePlaybackStore } from "../store/usePlaybackStore";

/** A pressed button exposes the active speed to sighted and assistive users. */
export function SpeedSelector() {
  const data = usePlaybackStore((state) => state.data);
  const speed = usePlaybackStore((state) => state.speed);
  const setSpeed = usePlaybackStore((state) => state.setSpeed);
  return (
    <div className="speed-selector">
      <span className="clock-heading" id="speed-label">Speed</span>
      <div className="segmented-control" role="group" aria-labelledby="speed-label">
        {PLAYBACK_SPEEDS.map((factor) => (
          <button key={factor} type="button" disabled={!data}
            aria-label={`${factor}× speed`} aria-pressed={factor === speed}
            onClick={() => setSpeed(factor)}>{factor}×</button>
        ))}
      </div>
    </div>
  );
}
