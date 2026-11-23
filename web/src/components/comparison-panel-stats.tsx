// AI contribution: 50% or more AI-generated
/**
 * Holding badge and running totals under one Compare panel (US-4.1, #230).
 *
 * Reads only the shared playback time, so both panels update on the same
 * clock tick. The numbers come from `comparisonStatsAt`.
 */
import { comparisonStatsAt } from "../lib/comparisonStats";
import { usePlaybackStore } from "../store/usePlaybackStore";
import type { StationViewData } from "../types/stationView";

interface ComparisonPanelStatsProps {
  /** The run this panel draws. */
  run: StationViewData;
}

/** Show whether a train is held now, and holds and connections so far. */
export function ComparisonPanelStats({ run }: Readonly<ComparisonPanelStatsProps>) {
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
      </dl>
    </div>
  );
}
