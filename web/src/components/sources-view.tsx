// AI contribution: 50% or more AI-generated
/**
 * Sources screen (US-7.2, #320): the Sources table for the selected
 * connection, with the values its run used beside each input's source.
 * Opened from the sidebar and from "Where these values come from" in Run
 * settings.
 */
import { useMemo } from "react";
import { buildSourceRows, FIXED_VALUE, runValues } from "../lib/parameter-sources";
import { DEFAULT_RUN_SETTINGS } from "../lib/run-settings";
import { usePlaybackStore } from "../store/usePlaybackStore";
import { useRunSettingsStore } from "../store/useRunSettingsStore";
import type { ParameterProvenanceMap } from "../types/provenance";
import { SourcesTable } from "./sources-table";

export function SourcesView({ provenance }: Readonly<{ provenance: ParameterProvenanceMap }>) {
  const connectionId = usePlaybackStore((state) => state.selectedConnectionId);
  const simulated = usePlaybackStore((state) =>
    connectionId !== null && state.simulatedConnectionIds.includes(connectionId));
  const applied = useRunSettingsStore((state) =>
    connectionId === null ? undefined : state.applied[connectionId]);
  // A loaded run without "Run scenario" used the API defaults; mock playback used none.
  const rows = useMemo(() => {
    const values = simulated ? runValues(applied ?? DEFAULT_RUN_SETTINGS) : {};
    return buildSourceRows(provenance, values);
  }, [provenance, simulated, applied]);

  return (
    <section className="panel sources-view" aria-labelledby="sources-title">
      <span className="clock-heading">Sources</span>
      <h1 id="sources-title">Where each value comes from</h1>
      <p className="sources-empty">
        {simulated
          ? `${FIXED_VALUE} means the run used the simulator's own value, which Run settings cannot change.`
          : "Mock playback uses no run settings, so no values are shown."}
      </p>
      {rows.length === 0
        ? <p className="sources-empty">No sources could be loaded from the simulation API.</p>
        : <SourcesTable rows={rows} unsetValue={simulated ? FIXED_VALUE : "—"} />}
    </section>
  );
}
