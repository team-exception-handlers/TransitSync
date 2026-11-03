// AI contribution: 50% or more AI-generated
import { formatTime } from "../lib/time";
import { usePlaybackStore } from "../store/usePlaybackStore";


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

  const duration = data?.duration_s ?? 0;

  const startClock = data?.start_clock_s ?? 0;

  const currentTimeFormatted = formatTime(
    currentTime,
    startClock
  );

  const endTimeFormatted = formatTime(
    duration,
    startClock
  );

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
          onChange={(event) => {
            const requestedTime = Number(
              event.target.value
            );

            seek(requestedTime);
          }}
        />

        {/* TIMELINE LABELS */}
        <div className="timeline-labels">

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