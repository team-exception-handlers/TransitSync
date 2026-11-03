// AI contribution: 50% or more AI-generated
/** Figma Play/Pause toggle reads and changes the real shared playback state. */
import { usePlaybackStore } from "../store/usePlaybackStore";

/** Keep native button behavior and accessible labels for icon-only actions. */
export function PlaybackControls() {
  const data = usePlaybackStore((state) => state.data);
  // Subscribe to boundaries, rather than rerendering buttons on every frame.
  const atStart = usePlaybackStore((state) => state.currentTime_s === 0);
  const atEnd = usePlaybackStore((state) => state.currentTime_s >= (state.data?.duration_s ?? 0));
  const playing = usePlaybackStore((state) => state.isPlaying);
  const play = usePlaybackStore((state) => state.play);
  const pause = usePlaybackStore((state) => state.pause);
  const rewind = usePlaybackStore((state) => state.rewind30);
  const label = playing ? "Pause" : "Play";

  return (
    <div className="playback-controls" role="group" aria-label="Playback controls">
      <button type="button" className="playback-button rewind" aria-label="Rewind 30 seconds"
        title="Rewind 30 seconds" disabled={!data || atStart} onClick={rewind}>
        <img src="/playback/rewind.svg" alt="" width="18" height="18" />
        <span>30 s</span>
      </button>
      <button type="button" className="playback-button primary" aria-label={label}
        title={label} disabled={!data || (!playing && atEnd)}
        onClick={playing ? pause : play}>
        <img src={`/playback/${playing ? "pause" : "play"}.svg`} alt="" width="18" height="18" />
      </button>
    </div>
  );
}
