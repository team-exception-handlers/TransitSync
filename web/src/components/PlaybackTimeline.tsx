// AI contribution: 50% or more AI-generated
/**
 * Playback timeline: the current and end clock times, the seek slider, and
 * diamond markers where the Adaptive strategy switched mode (#60).
 */
import { useMemo } from "react";
import { modeLabel, modeSwitchMarkers } from "../lib/modeSwitches";
import { formatTime } from "../lib/time";
import { usePlaybackStore } from "../store/usePlaybackStore";
import "./playback-timeline.css";

/**
 * Reads the run and playback position from the shared store and writes back
 * only through `seek`, so the slider, the clock and the Canvas always agree.
 * It holds no time state of its own.
 */
export function PlaybackTimeline() {
  const data = usePlaybackStore(
    (state) => state.data
  );

  const currentTime = usePlaybackStore(
    (state) => state.currentTime_s
  );

  const seek = usePlaybackStore(
    (state) => state.seek
  );

  // Without a run the slider spans 0 to 0 and is disabled below.
  const duration = data?.duration_s ?? 0;

  // Run times are seconds from the run start; labels show local clock time.
  const startClock = data?.start_clock_s ?? 0;

  const currentTimeFormatted = formatTime(
    currentTime,
    startClock
  );

  const endTimeFormatted = formatTime(
    duration,
    startClock
  );

  // Derived from the run only, so a playing clock does not recompute it.
  const modeSwitches = useMemo(() => modeSwitchMarkers(data), [data]);

  return (
    <div className="playback-timeline">

      {/* CURRENT SIMULATION TIME */}
      <div className="timeline-clock">
        <span className="timeline-clock-current">
          {currentTimeFormatted}
        </span>

        <span className="timeline-clock-separator">
          /
        </span>

        <span className="timeline-clock-end">
          {endTimeFormatted}
        </span>
      </div>

      {/* FUNCTIONAL SEEKING SLIDER */}
      <div className="timeline-container">

        <input
          type="range"
          className="timeline-slider"
          min={0}
          max={duration}
          step={0.1}
          value={currentTime}
          disabled={!data}
          aria-label="Seek simulation time"
          aria-valuetext={currentTimeFormatted}
          // Dragging in either direction seeks; the store clamps to the run.
          onChange={(event) => {
            const requestedTime = Number(
              event.target.value
            );

            seek(requestedTime);
          }}
        />

        {/* ADAPTIVE MODE SWITCHES */}
        {/* Rendered only when the run has switches, so other strategies show a plain timeline. */}
        {modeSwitches.length > 0 && (
          <ul className="timeline-markers" aria-label="Adaptive mode switches">
            {modeSwitches.map((marker) => {
              const label = `Mode switch at ${formatTime(marker.time_s, startClock)}: `
                + `${modeLabel(marker.from_mode)} to ${modeLabel(marker.to_mode)}`;
              return (
                <li key={marker.id} className="timeline-marker" title={label}
                  style={{ left: `${marker.fraction * 100}%` }}>
                  {/* The diamond is drawn in CSS; this text is what a screen reader reads. */}
                  <span className="visually-hidden">{label}</span>
                </li>
              );
            })}
          </ul>
        )}

        {/* TIMELINE LABELS */}
        <div className="timeline-labels">

          {/* Five evenly spaced clock labels, hours and minutes only. */}
          {[0, 0.25, 0.5, 0.75, 1].map(
            (fraction) => {

              const timestamp =
                duration * fraction;

              return (
                <span key={fraction}>
                  {formatTime(
                    timestamp,
                    startClock
                  ).slice(0, 5)}
                </span>
              );
            }
          )}

        </div>

      </div>

    </div>
  );
}