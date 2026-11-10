// AI contribution: 50% or more AI-generated
/**
 * Front-end client for the FastAPI simulation run endpoint (#79).
 *
 * The station view asks the API for the run output of the selected connection
 * and gets back the same map-ready shape as the bundled mock runs. Every
 * response goes through the station-view validator before the store sees it,
 * so a bad or partial response can never reach the Canvas or the clock.
 */
import type { StationViewData } from "../types/stationView";
import { parseStationViewData } from "./validateStationView";

/** Loads one run for a connection ID; the store accepts any function of this shape. */
export type ConnectionRunLoader = (
  connectionId: string,
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

/** Pull FastAPI's `detail` text out of an error body, if it is a plain string. */
async function errorDetail(response: Response): Promise<string | null> {
  try {
    const body: unknown = await response.json();
    if (typeof body === "object" && body !== null && "detail" in body) {
      const { detail } = body as { detail: unknown };
      // 422 responses carry a list of field errors; only a string is shown as-is.
      return typeof detail === "string" ? detail : null;
    }
  } catch {
    // A non-JSON error body (for example a proxy page) falls back to the status.
  }
  return null;
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
    const response = await fetchImpl(`${baseUrl}/simulation/run`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ connection_id: connectionId }),
      signal,
    });
    if (!response.ok) {
      const detail = await errorDetail(response);
      throw new SimulationRunError(
        detail ?? `Simulation run failed (HTTP ${response.status})`,
        response.status,
      );
    }
    const run = parseStationViewData(await response.json());
    // The selector, heading and passenger filter all key on this ID, so a run
    // for another connection would show the wrong station under the right name.
    if (!run.connections.some((connection) => connection.id === connectionId)) {
      throw new SimulationRunError(`Run does not contain connection: ${connectionId}`);
    }
    return run;
  };
}
