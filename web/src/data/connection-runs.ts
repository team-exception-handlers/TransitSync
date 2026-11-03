// AI contribution: 50% or more AI-generated
/** Synthetic runs for the three documented interchanges, using saved platform IDs. */
import rawMapping from "./interchange_mapping.json";
import rawMock from "./mock-interchange.json";
import { stationViewData } from "./stationViewData";
import { buildStationViewData } from "../lib/buildStationViewData";
import type { InterchangeMapping, MockInterchangeData } from "../types/stationView";

const mapping = rawMapping as InterchangeMapping;

/** Adapt the McGill fixture's geometry/pulse; these are mock runs, not GTFS runs. */
function buildMockRun(interchangeId: string, label: string) {
  const mock = structuredClone(rawMock) as MockInterchangeData;
  const entries = Object.values(mapping).flat().filter((item) => item.interchange_id === interchangeId);
  const replacements = new Map(stationViewData.platforms.map((source) => {
    const target = entries.find((item) => item.direction_id === source.direction_id &&
      (item.line_id === "rem") === (source.line_id === "rem"));
    if (!target) throw new Error(`Unavailable mock platform: ${source.platform_id}`);
    return [source.platform_id, target];
  }));
  const platformId = (id: string) => replacements.get(id)!.platform_id;
  const metro = entries.find((item) => item.line_id !== "rem")!;
  const connectionId = `${interchangeId}-rem-${metro.line_id}`;

  // Keep all references aligned with the mapping adapter and validator contracts.
  mock.interchange = { id: interchangeId, name: label };
  mock.stations = mock.stations.map((station) => ({
    ...station,
    name: station.line_id === "rem" ? `${label} REM` : metro.stop_name,
    line_id: station.line_id === "rem" ? "rem" : metro.line_id,
  }));
  mock.platform_layouts = Object.fromEntries(Object.entries(mock.platform_layouts)
    .map(([id, layout]) => [platformId(id), layout]));
  mock.corridors = mock.corridors.map((item) => ({ ...item,
    from_platform_id: platformId(item.from_platform_id), to_platform_id: platformId(item.to_platform_id),
  }));
  mock.connections = mock.connections.map((item) => ({ ...item, id: connectionId, label,
    from_platform_id: platformId(item.from_platform_id), to_platform_id: platformId(item.to_platform_id),
  }));
  mock.passenger_tracks = mock.passenger_tracks.map((track) => ({ ...track, connection_id: connectionId }));
  mock.train_events = mock.train_events.map((event) => ({ ...event,
    platform_id: platformId(event.platform_id), station_id: replacements.get(event.platform_id)!.stop_id,
  }));
  return buildStationViewData(mapping, mock);
}

// Names come from #76 and the backend interchange mapping, not presentation state.
export const connectionRuns = [
  buildMockRun("gare_centrale_bonaventure", "Gare Centrale ↔ Bonaventure"),
  stationViewData,
  buildMockRun("edouard_montpetit", "Édouard-Montpetit"),
];
