// AI contribution: Below 50% AI-generated

import rawMapping from "./interchange_mapping.json";
import rawMock from "./mock-interchange.json";

import { buildStationViewData } from "../lib/buildStationViewData";

import type {
    InterchangeMapping,
    MockInterchangeData,
} from "../types/stationView";

const mapping = rawMapping as unknown as InterchangeMapping;

const mock = rawMock as unknown as MockInterchangeData;

export const stationViewData = buildStationViewData(mapping, mock);