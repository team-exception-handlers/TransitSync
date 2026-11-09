// AI contribution: 50% or more AI-generated
/** Every selectable mock preserves actual mapping identities and event references. */
import { describe, expect, it } from "vitest";
import { connectionRuns } from "../../src/data/connection-runs";
import mapping from "../../src/data/interchange_mapping.json";
import { parseStationViewData } from "../../src/lib/validateStationView";

describe("connection mock catalog", () => {
  it.each(connectionRuns)("validates $interchange.id with its real backend platform metadata", (run) => {
    expect(parseStationViewData(run)).toStrictEqual(run);
    expect(run.platforms).toHaveLength(4);
    for (const platform of run.platforms) {
      expect(Object.values(mapping).flat()).toContainEqual(expect.objectContaining({
        platform_id: platform.platform_id, interchange_id: run.interchange.id,
        stop_id: platform.stop_id, direction_label: platform.direction_label,
      }));
    }
    expect(run.passenger_tracks.every((track) => track.connection_id === run.connections[0].id)).toBe(true);
  });
});
