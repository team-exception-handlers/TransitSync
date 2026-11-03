// AI contribution: 50% or more AI-generated
/** Isolate the ticking clock so the full application shell does not rerender. */
import { formatTime } from "../lib/time";
import { usePlaybackStore } from "../store/usePlaybackStore";

/** Display simulation seconds using the loaded run's clock offset. */
export function SimulationClock() {
  const data = usePlaybackStore((state) => state.data);
  const time = usePlaybackStore((state) => state.currentTime_s);
  return (
    <section className="panel clock-panel">
      <div className="clock-heading">Simulation clock</div>
      <div className="clock-digits">{formatTime(time, data?.start_clock_s ?? 0)}</div>
    </section>
  );
}
