// AI contribution: 50% or more AI-generated
/**
 * Results screen (#408). For now it holds the passenger delay chart, which
 * moved here from the bottom of the station view; later result stories add
 * their panels to this screen.
 */
import { DelayChart } from "../components/DelayChart";
import { usePlaybackStore } from "../store/usePlaybackStore";

/** Show the delay chart, or say why there is nothing to chart yet. */
export function ResultsView() {
  // Only simulator output carries a time series; the bundled mocks do not.
  const hasTimeSeries = usePlaybackStore((state) => Boolean(state.data?.time_series));

  return (
    <>
      <h1 className="view-title">Results</h1>
      {hasTimeSeries ? (
        <DelayChart />
      ) : (
        <p className="panel view-message">
          Results appear here once a simulation run is loaded. Run a scenario
          from Scenario setup to see passenger delay over time.
        </p>
      )}
    </>
  );
}
