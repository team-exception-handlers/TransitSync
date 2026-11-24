// AI contribution: 50% or more AI-generated
/**
 * Front-end client for the FastAPI simulation run endpoint (#79).
 *
 * The station view asks the API for the run output of the selected connection
 * and gets back the same map-ready shape as the bundled mock runs. Every
 * response goes through the station-view validator before the store sees it,
 * so a bad or partial response can never reach the Canvas or the clock.
 *
 * Two callers share the request code: the connection loader (API default
 * settings) and `runSimulation`, which sends the run settings panel's values
 * and turns every failure into a sentence a user can act on.
 *
 * `runComparison` (US-4.1, #230) sends the same settings to
 * `/simulation/comparison` and gets a holding and a no-holding run back,
 * each checked exactly like a single run, plus the passengers holding
 * helped or harmed (#285).
 */
import type { LineId, StationViewData } from "../types/stationView";
import type { RunSettings } from "../types/runSettings";
import { buildRunRequest } from "./run-settings";
import { parseStationViewData } from "./validateStationView";
import type { ParameterProvenance, ParameterProvenanceMap } from "../types/provenance";
import { normalizeClassification } from "../types/provenance";

/** Loads one run for a connection ID; the store accepts any function of this shape. */
export type ConnectionRunLoader = (
  connectionId: string,
  signal?: AbortSignal,
) => Promise<StationViewData>;

/**
 * One backend-listed connection: identity, metro line, and interchange (#76).
 * Matches the shape of `GET /connections`; field names stay snake_case so the
 * JSON maps onto this type without renaming.
 */
export interface ConnectionSummary {
  id: string;
  label: string;
  metro_line_id: LineId;
  interchange: { id: string; name: string };
}

/** Loads the backend's full connection catalog; the store accepts any function of this shape. */
export type ConnectionCatalogLoader = (signal?: AbortSignal) => Promise<ConnectionSummary[]>;

const KNOWN_LINE_IDS: readonly LineId[] = ["rem", "orange", "green", "blue"];

function isNonEmptyString(value: unknown): value is string {
  return typeof value === "string" && value.length > 0;
}

function isConnectionSummary(value: unknown): value is ConnectionSummary {
  if (typeof value !== "object" || value === null) return false;
  const item = value as Record<string, unknown>;
  const interchange = item.interchange;
  if (typeof interchange !== "object" || interchange === null) return false;
  const interchangeFields = interchange as Record<string, unknown>;
  return (
    isNonEmptyString(item.id) &&
    isNonEmptyString(item.label) &&
    KNOWN_LINE_IDS.includes(item.metro_line_id as LineId) &&
    isNonEmptyString(interchangeFields.id) &&
    isNonEmptyString(interchangeFields.name)
  );
}

/**
 * Validate the `/connections` list response. Throws if the body is not an
 * array or any entry is missing a field or names an unknown metro line, so
 * the selector never renders a connection it cannot describe.
 */
export function parseConnectionSummaries(value: unknown): ConnectionSummary[] {
  if (!Array.isArray(value)) {
    throw new Error("Connection list response is not an array");
  }
  if (value.some((item) => !isConnectionSummary(item))) {
    throw new Error("Invalid connection summary in catalog response");
  }
  return value as ConnectionSummary[];
}

/**
 * Runs the selected connection with the panel's settings; the panel accepts
 * any function of this shape, so tests can pass a fake.
 */
export type ScenarioRunner = (
  connectionId: string,
  settings: RunSettings,
  signal?: AbortSignal,
) => Promise<StationViewData>;

/** A request that reached the API but did not return a usable run. */
export class SimulationRunError extends Error {
  readonly status: number | null;

  constructor(message: string, status: number | null = null) {
    super(message);
    this.name = "SimulationRunError";
    this.status = status;
  }
}

/**
 * Read the API base URL from `VITE_API_URL`, without trailing slashes.
 * Returns null when it is unset or blank: the app then uses mock runs only.
 */
export function configuredApiUrl(
  value: string | undefined = import.meta.env.VITE_API_URL,
): string | null {
  const trimmed = value?.trim() ?? "";
  if (trimmed === "") return null;
  let end = trimmed.length;
  while (end > 0 && trimmed[end - 1] === "/") end -= 1;
  return trimmed.slice(0, end);
}

/** Read FastAPI's `detail` from an error body; null when there is none. */
async function errorDetail(response: Response): Promise<unknown> {
  try {
    const body: unknown = await response.json();
    if (typeof body === "object" && body !== null && "detail" in body) {
      return (body as { detail: unknown }).detail;
    }
  } catch {
    // A non-JSON error body (for example a proxy page) falls back to the status.
  }
  return null;
}

/** POST one JSON body to a simulation endpoint; network errors pass through. */
function postRun(
  baseUrl: string,
  body: unknown,
  fetchImpl: typeof fetch,
  signal?: AbortSignal,
  path = "/simulation/run",
): Promise<Response> {
  return fetchImpl(`${baseUrl}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });
}

/** Validate a run payload and check that it holds the requested connection. */
function checkedRun(payload: unknown, connectionId: string): StationViewData {
  const run = parseStationViewData(payload);
  // The selector, heading and passenger filter all key on this ID, so a run
  // for another connection would show the wrong station under the right name.
  if (!run.connections.some((connection) => connection.id === connectionId)) {
    throw new SimulationRunError(`Run does not contain connection: ${connectionId}`);
  }
  return run;
}

/**
 * Build a loader that POSTs `{connection_id}` to `/simulation/run` at `baseUrl`
 * (API default settings) and returns the validated run. `fetchImpl` is for tests.
 * Throws `SimulationRunError` on an HTTP failure (404: unknown connection) or a
 * run without the connection; validation and network errors pass through.
 */
export function createConnectionRunLoader(
  baseUrl: string,
  fetchImpl: typeof fetch = fetch,
): ConnectionRunLoader {
  return async (connectionId, signal) => {
    const response = await postRun(baseUrl, { connection_id: connectionId }, fetchImpl, signal);
    if (!response.ok) {
      const detail = await errorDetail(response);
      // 422 responses carry a list of field errors; only a string is shown as-is.
      throw new SimulationRunError(
        typeof detail === "string" ? detail : `Simulation run failed (HTTP ${response.status})`,
        response.status,
      );
    }
    return checkedRun(await response.json(), connectionId);
  };
}

/**
 * Build a loader that GETs `${baseUrl}/connections` (#76) and returns the
 * validated catalog. `fetchImpl` is for tests. Throws `SimulationRunError`
 * on an HTTP failure; validation and network errors pass through.
 */
export function createConnectionCatalogLoader(
  baseUrl: string,
  fetchImpl: typeof fetch = fetch,
): ConnectionCatalogLoader {
  return async (signal) => {
    const response = await fetchImpl(`${baseUrl}/connections`, { signal });
    if (!response.ok) {
      throw new SimulationRunError(
        `Could not load the connection list (HTTP ${response.status}).`,
        response.status,
      );
    }
    return parseConnectionSummaries(await response.json());
  };
}

/**
 * Turn FastAPI's 422 `detail` list into "field: message" text. Each entry has
 * a `loc` path (starting with "body") and a `msg`; anything else is skipped.
 */
function fieldErrors(detail: unknown): string | null {
  if (!Array.isArray(detail)) return null;
  const parts = detail.flatMap((item: unknown) => {
    if (typeof item !== "object" || item === null) return [];
    const { loc, msg } = item as { loc?: unknown; msg?: unknown };
    if (typeof msg !== "string") return [];
    const field = Array.isArray(loc) ? loc.filter((part) => part !== "body").join(".") : "";
    return [field === "" ? msg : `${field}: ${msg}`];
  });
  return parts.length === 0 ? null : parts.join("; ");
}

/** Sentence shown to the user for one failed HTTP status. */
async function failureMessage(response: Response): Promise<string> {
  const detail = await errorDetail(response);
  if (response.status === 404) {
    return "The simulator does not have this connection. Choose another connection and run again.";
  }
  if (response.status === 422) {
    const fields = fieldErrors(detail) ?? "check the values and run again";
    return `The simulator rejected these settings (${fields}).`;
  }
  // 5xx details are internal, so only the status is shown.
  return `The simulation run failed on the server (HTTP ${response.status}). Try again in a moment.`;
}

/** Where and how `runSimulation` sends its request. */
export interface RunSimulationOptions {
  /** API origin without a trailing slash, from `configuredApiUrl`. */
  baseUrl: string;
  signal?: AbortSignal;
  /** Replaces the global fetch in tests. */
  fetchImpl?: typeof fetch;
}

/**
 * Run `connectionId` with the panel's `settings` and return the validated run.
 *
 * Every failure is thrown as a `SimulationRunError` whose message is safe to
 * show: API unreachable, unknown connection (404), rejected settings (422),
 * server failure, or a response the station view cannot display. An aborted
 * request rethrows the abort unchanged so callers can ignore it.
 */
export function runSimulation(
  connectionId: string,
  settings: RunSettings,
  options: RunSimulationOptions,
): Promise<StationViewData> {
  return requestRun("/simulation/run", connectionId, settings, options,
    (payload) => checkedRun(payload, connectionId));
}

/**
 * Send the panel's settings to `path` and parse the reply with `parse`.
 * Shared by single runs and comparisons so both explain failures the same
 * way; see `runSimulation` for the errors it throws.
 */
async function requestRun<T>(
  path: string,
  connectionId: string,
  settings: RunSettings,
  { baseUrl, signal, fetchImpl = fetch }: RunSimulationOptions,
  parse: (payload: unknown) => T,
): Promise<T> {
  let response: Response;
  try {
    const body = buildRunRequest(connectionId, settings);
    response = await postRun(baseUrl, body, fetchImpl, signal, path);
  } catch (error) {
    if (signal?.aborted) throw error;
    // fetch rejects before any response: server down, wrong URL or blocked by CORS.
    throw new SimulationRunError(
      `Could not reach the simulation API at ${baseUrl}. Check that the backend is running.`,
    );
  }
  if (!response.ok) {
    throw new SimulationRunError(await failureMessage(response), response.status);
  }
  try {
    return parse(await response.json());
  } catch (error) {
    // A cancel while the body is still being read rejects json() with the
    // abort; pass it through unchanged, as for a cancel during fetch above.
    if (signal?.aborted) throw error;
    const reason = error instanceof Error ? error.message : String(error);
    throw new SimulationRunError(
      `The simulator returned a run the station view cannot display (${reason}).`,
      response.status,
    );
  }
}

/** What both runs of a comparison share, shown so users can see they match. */
export interface StartingConditions {
  /** Service date both runs simulate, as an ISO date (YYYY-MM-DD). */
  serviceDate: string;
  /** Master seed: the same random draws feed both runs. */
  masterSeed: number;
  /** Run length in seconds. */
  duration_s: number;
}

/**
 * Passengers the holding run left better off, worse off or unaffected
 * (within 30 s) versus no holding, with the time each group gained or lost
 * in seconds (US-6.3, #285). Averages are null for an empty group.
 */
export interface PassengerSplit {
  better_off: number;
  worse_off: number;
  unaffected: number;
  not_compared: number;
  total_time_saved_s: number;
  total_time_lost_s: number;
  average_time_saved_s: number | null;
  average_time_lost_s: number | null;
}

/** A holding run and a no-holding run of one connection (US-4.1, #230). */
export interface SimulationComparison {
  holding: StationViewData;
  noHolding: StationViewData;
  /** Strategy the holding side used, for example "connection_protection". */
  holdingStrategy: string;
  startingConditions: StartingConditions;
  passengerSplit: PassengerSplit;
}

/** Runs both sides of a comparison; the Compare screen accepts any function of this shape. */
export type ComparisonRunner = (
  connectionId: string,
  settings: RunSettings,
  signal?: AbortSignal,
) => Promise<SimulationComparison>;

const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;

/** Check the shared fields of a comparison body; throws on the first bad one. */
function checkStartingConditions(body: Record<string, unknown>): StartingConditions {
  const { service_date, master_seed, duration_s } = body;
  if (typeof service_date !== "string" || !ISO_DATE.test(service_date)) {
    throw new TypeError("Invalid comparison service date");
  }
  if (typeof master_seed !== "number" || !Number.isInteger(master_seed) || master_seed < 0) {
    throw new TypeError("Invalid comparison master seed");
  }
  if (typeof duration_s !== "number" || !Number.isFinite(duration_s) || duration_s <= 0) {
    throw new TypeError("Invalid comparison duration");
  }
  return { serviceDate: service_date, masterSeed: master_seed, duration_s };
}

const SPLIT_COUNTS = ["better_off", "worse_off", "unaffected", "not_compared"] as const;
const SPLIT_TOTALS = ["total_time_saved_s", "total_time_lost_s"] as const;
const SPLIT_AVERAGES = ["average_time_saved_s", "average_time_lost_s"] as const;

const isNonNegative = (value: unknown): value is number =>
  typeof value === "number" && Number.isFinite(value) && value >= 0;

/** Check the passenger split; counts are whole numbers and no time is negative. */
function checkPassengerSplit(value: unknown): PassengerSplit {
  const split = (typeof value === "object" && value !== null ? value : {}) as Record<string, unknown>;
  const valid = SPLIT_COUNTS.every((key) => isNonNegative(split[key]) && Number.isInteger(split[key]))
    && SPLIT_TOTALS.every((key) => isNonNegative(split[key]))
    && SPLIT_AVERAGES.every((key) => split[key] === null || isNonNegative(split[key]));
  if (!valid) throw new TypeError("Invalid comparison passenger split");
  return split as unknown as PassengerSplit;
}

/**
 * Validate a `/simulation/comparison` body for `connectionId`. Each side goes
 * through the same checks as a single run, and both must last as long as the
 * shared duration, because one playback clock drives both panels.
 */
export function parseSimulationComparison(
  value: unknown,
  connectionId: string,
): SimulationComparison {
  if (typeof value !== "object" || value === null) {
    throw new TypeError("Comparison response must be an object");
  }
  const body = value as Record<string, unknown>;
  const startingConditions = checkStartingConditions(body);
  if (!isNonEmptyString(body.holding_strategy)) {
    throw new TypeError("Invalid comparison holding strategy");
  }
  const holding = checkedRun(body.holding, connectionId);
  const noHolding = checkedRun(body.no_holding, connectionId);
  if (holding.duration_s !== startingConditions.duration_s
    || noHolding.duration_s !== startingConditions.duration_s) {
    throw new TypeError("Comparison runs do not share one duration");
  }
  const passengerSplit = checkPassengerSplit(body.passenger_split);
  return { holding, noHolding, holdingStrategy: body.holding_strategy, startingConditions, passengerSplit };
}

/**
 * Run `connectionId` with and without holding, using the panel's `settings`,
 * and return both validated runs. Failures are thrown as `SimulationRunError`
 * with the same user-facing messages as `runSimulation`.
 */
export function runComparison(
  connectionId: string,
  settings: RunSettings,
  options: RunSimulationOptions,
): Promise<SimulationComparison> {
  return requestRun("/simulation/comparison", connectionId, settings, options,
    (payload) => parseSimulationComparison(payload, connectionId));
}

export type ParameterProvenanceLoader = (
  signal?: AbortSignal,
) => Promise<ParameterProvenanceMap>;

function isProvenanceEntryRecord(
  value: unknown,
): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/**
 * Validate and normalize the `/parameters` provenance response into a map
 * keyed by parameter name. Throws if the top-level payload is not a JSON object;
 * a single malformed entry is skipped instead, so it cannot hide every badge.
 */
export function parseParameterProvenance(
  payload: unknown,
): ParameterProvenanceMap {
  if (!isProvenanceEntryRecord(payload)) {
    throw new Error("Parameter provenance response is not an object");
  }

  const result: ParameterProvenanceMap = {};
  for (const [key, rawEntry] of Object.entries(payload)) {
    // Skip one malformed entry, like an unknown classification: that parameter
    // reads "Unspecified" while every other badge still shows its source.
    if (!isProvenanceEntryRecord(rawEntry)) continue;

    const entry: ParameterProvenance = {
      classification: normalizeClassification(
        typeof rawEntry.classification === "string"
          ? rawEntry.classification
          : null,
      ),
      source_name:
        typeof rawEntry.source_name === "string" ? rawEntry.source_name : "",
      source_link:
        typeof rawEntry.source_link === "string" ? rawEntry.source_link : "",
    };
    result[key] = entry;
  }

  return result;
}

/**
 * Build a loader that GETs `${baseUrl}/parameters` and returns the validated
 * provenance map. `fetchImpl` is for tests.
 */
export function createParameterProvenanceLoader(
  baseUrl: string,
  fetchImpl: typeof fetch = fetch,
): ParameterProvenanceLoader {
  return async (signal) => {
    const response = await fetchImpl(`${baseUrl}/parameters`, { signal });
    if (!response.ok) {
      throw new SimulationRunError(
        `Could not load parameter provenance (HTTP ${response.status}).`,
        response.status,
      );
    }
    return parseParameterProvenance(await response.json());
  };
}
