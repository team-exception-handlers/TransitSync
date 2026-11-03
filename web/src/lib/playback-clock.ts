// AI contribution: 50% or more AI-generated
/** Observer bridge: the store owns playback; one animation frame requests a tick. */
import { usePlaybackStore } from "../store/usePlaybackStore";

// Multiple mounted consumers lease one clock, including StrictMode remounts.
let owners = 0;
let detach: (() => void) | null = null;

/** Attach one Observer subscription; components never own independent timers. */
function attachClock(): () => void {
  let frame: number | null = null;
  const schedule = () => {
    // Store notifications may fire during a frame; never queue a second frame.
    if (usePlaybackStore.getState().isPlaying && frame === null) {
      frame = requestAnimationFrame(() => {
        frame = null;
        usePlaybackStore.getState().advance();
        schedule();
      });
    } else if (!usePlaybackStore.getState().isPlaying && frame !== null) {
      cancelAnimationFrame(frame);
      frame = null;
    }
  };
  const unsubscribe = usePlaybackStore.subscribe(schedule);
  schedule();
  return () => {
    unsubscribe();
    if (frame !== null) cancelAnimationFrame(frame);
    usePlaybackStore.getState().pause();
  };
}

/** Lease the shared clock and release it exactly once on effect cleanup. */
export function startPlaybackClock(): () => void {
  if (owners === 0) detach = attachClock();
  owners += 1;
  let released = false;
  return () => {
    if (released) return;
    released = true;
    owners -= 1;
    // Unmounting one view must not stop another view of the same run.
    if (owners === 0) {
      detach?.();
      detach = null;
    }
  };
}
