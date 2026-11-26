// AI contribution: 50% or more AI-generated
/**
 * Holding badge and running totals under one Compare panel (US-4.1, #230),
 * then the time saved and lost so far against the other side (US-4.3), and
 * the summary under both panels.
 *
 * Reads only the shared playback time, so both panels update on the same
 * clock tick. The numbers come from `comparisonStatsAt` and `splitAt`.
 */
import {
  comparisonStatsAt, formatDuration, splitAt, type ComparedPair,
} from "../lib/comparisonStats";
import { usePlaybackStore } from "../store/usePlaybackStore";
import type { StationViewData } from "../types/stationView";

interface ComparisonPanelStatsProps {
  /** The run this panel draws. */
  run: StationViewData;
  /** Both runs, for the time saved and lost; absent until the split loads. */
  pair?: ComparedPair;
  /** Which run of the pair this panel is. */
  side: "holding" | "noHolding";
}

const passengers = (count: number) => `${count} passenger${count === 1 ? "" : "s"}`;

/** Show whether a train is held now, and holds, connections and time so far. */
export function ComparisonPanelStats({ run, pair, side }: Readonly<ComparisonPanelStatsProps>) {
  const time = usePlaybackStore((state) => state.currentTime_s);
  const stats = comparisonStatsAt(run, time);
  const change = pair && splitAt(pair, time)[side];

  return (
    <div className="comparison-stats">
      {/* Text as well as colour, so the state reads without colour vision. */}
      {stats.holdingNow && <span className="hold-badge">Holding</span>}
      <dl className="comparison-stats-values">
        <div><dt>Holds so far</dt><dd>{stats.holds}</dd></div>
        <div><dt>Connections made</dt><dd>{stats.made}</dd></div>
        <div><dt>Connections missed</dt><dd>{stats.missed}</dd></div>
        {/* Only passengers outside the threshold; the summary has the rest. */}
        {change && (
          <>
            <div>
              <dt>Time saved (better off)</dt>
              <dd>{formatDuration(change.saved_s)} · {passengers(change.savedPassengers)}</dd>
            </div>
            <div>
              <dt>Time lost (worse off)</dt>
              <dd>{formatDuration(change.lost_s)} · {passengers(change.lostPassengers)}</dd>
            </div>
          </>
        )}
      </dl>
    </div>
  );
}

/** Net change for every compared passenger, as one phrase about holding. */
function netPhrase(net_s: number): string {
  if (Math.round(net_s) === 0) return "no net change";
  return `holding ${net_s < 0 ? "saved" : "cost"} ${formatDuration(Math.abs(net_s))} in total`;
}

/**
 * The passengers the panels leave out (unaffected and not yet compared) and
 * the net change over everyone compared, so the panels are not read as the
 * whole effect of holding.
 */
export function ComparisonSplitSummary({ pair }: Readonly<{ pair: ComparedPair }>) {
  const time = usePlaybackStore((state) => state.currentTime_s);
  const split = splitAt(pair, time);
  const threshold = formatDuration(pair.threshold_s);
  return (
    <p className="comparison-note">
      So far: {passengers(split.unaffected)} unaffected ({threshold} or less),{" "}
      {split.notCompared} not compared yet (not left in either run), and{" "}
      {netPhrase(split.net_s)}. Each passenger is compared by when they left on
      their connecting train in both runs.
    </p>
  );
}
