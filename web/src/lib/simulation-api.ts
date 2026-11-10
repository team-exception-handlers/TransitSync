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
 */
import type { RunSettings } from "../types/runSettings";
import type { StationViewData } from "../types/stationView";
import { buildRunRequest } from "./run-settings";
import { parseStationViewData } from "./validateStationView";

/** Loads one run for a connection ID; the store accepts any function of this shape. */
export type ConnectionRunLoader = (
  connectionId: string,
  signal?: AbortSignal,
) => Promise<StationViewData>;

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
  return trimmed === "" ? null : trimmed.replace(/\/+$/, "");
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

/** POST one JSON body to the run endpoint; network errors pass through. */
function postRun(
  baseUrl: string,
  body: unknown,
  fetchImpl: typeof fetch,
  signal?: AbortSignal,
): Promise<Response> {
  return fetchImpl(`${baseUrl}/simulation/run`, {
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
export async function runSimulation(
  connectionId: string,
  settings: RunSettings,
  { baseUrl, signal, fetchImpl = fetch }: RunSimulationOptions,
): Promise<StationViewData> {
  let response: Response;
  try {
    response = await postRun(baseUrl, buildRunRequest(connectionId, settings), fetchImpl, signal);
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
    return checkedRun(await response.json(), connectionId);
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
