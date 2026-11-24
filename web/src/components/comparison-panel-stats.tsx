// AI contribution: 50% or more AI-generated
/**
 * Holding badge and running totals under one Compare panel (US-4.1, #230),
 * then the whole-run time saved and lost against the other side (US-4.3).
 *
 * Reads only the shared playback time, so both panels update on the same
 * clock tick. The numbers come from `comparisonStatsAt`.
 */
import { comparisonStatsAt, formatDuration, type TimeChange } from "../lib/comparisonStats";
import { usePlaybackStore } from "../store/usePlaybackStore";
import type { StationViewData } from "../types/stationView";

interface ComparisonPanelStatsProps {
  /** The run this panel draws. */
  run: StationViewData;
  /** This side's time saved and lost against the other run, once loaded. */
  timeChange?: TimeChange;
}

const passengers = (count: number) => `${count} passenger${count === 1 ? "" : "s"}`;

/** Show whether a train is held now, and holds and connections so far. */
export function ComparisonPanelStats({ run, timeChange }: Readonly<ComparisonPanelStatsProps>) {
  const time = usePlaybackStore((state) => state.currentTime_s);
  const stats = comparisonStatsAt(run, time);

  return (
    <div className="comparison-stats">
      {/* Text as well as colour, so the state reads without colour vision. */}
      {stats.holdingNow && <span className="hold-badge">Holding</span>}
      <dl className="comparison-stats-values">
        <div><dt>Holds so far</dt><dd>{stats.holds}</dd></div>
        <div><dt>Connections made</dt><dd>{stats.made}</dd></div>
        <div><dt>Connections missed</dt><dd>{stats.missed}</dd></div>
        {/* Whole-run totals: the split compares finished journeys, not a moment. */}
        {timeChange && (
          <>
            <div>
              <dt>Time saved (whole run)</dt>
              <dd>{formatDuration(timeChange.saved_s)} · {passengers(timeChange.savedPassengers)}</dd>
            </div>
            <div>
              <dt>Time lost (whole run)</dt>
              <dd>{formatDuration(timeChange.lost_s)} · {passengers(timeChange.lostPassengers)}</dd>
            </div>
          </>
        )}
      </dl>
    </div>
  );
}
