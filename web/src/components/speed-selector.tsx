// AI contribution: 50% or more AI-generated
/**
 * Figma speed segments use the store's single supported-speed contract.
 * The view subscribes only to speed and data, so normal frame updates do not
 * rerender a control whose selection has not changed.
 */
import { useId } from "react";
import { PLAYBACK_SPEEDS } from "../types/playback-speed";
import { usePlaybackStore } from "../store/usePlaybackStore";

/** A pressed button exposes the active speed to sighted and assistive users. */
export function SpeedSelector() {
  // Distinct IDs keep labels valid if another playback view is mounted later.
  const labelId = useId();
  const data = usePlaybackStore((state) => state.data);
  const speed = usePlaybackStore((state) => state.speed);
  const setSpeed = usePlaybackStore((state) => state.setSpeed);
  return (
    <div className="speed-selector">
      <span className="clock-heading" id={labelId}>Speed</span>
      <div className="segmented-control" role="group" aria-labelledby={labelId}>
        {PLAYBACK_SPEEDS.map((factor) => (
          <button key={factor} type="button" disabled={!data}
            aria-label={`${factor}× speed`} aria-pressed={factor === speed}
            onClick={() => setSpeed(factor)}>{factor}×</button>
        ))}
      </div>
    </div>
  );
}
