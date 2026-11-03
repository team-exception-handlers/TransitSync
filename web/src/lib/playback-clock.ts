// AI contribution: 50% or more AI-generated
/** Observer bridge: the store owns playback; one animation frame requests a tick. */
import { usePlaybackStore } from "../store/usePlaybackStore";

/** Attach the app clock and return cleanup for React's effect lifecycle. */
export function startPlaybackClock(): () => void {
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
