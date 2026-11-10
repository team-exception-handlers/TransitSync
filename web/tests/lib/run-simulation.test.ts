// AI contribution: 50% or more AI-generated
/** runSimulation sends the panel's settings and explains every failure (#45, #50, #60). */
import { describe, expect, it, vi } from "vitest";
import { stationViewData } from "../../src/data/stationViewData";
import { DEFAULT_RUN_SETTINGS } from "../../src/lib/run-settings";
import { SimulationRunError, runSimulation } from "../../src/lib/simulation-api";

const CONNECTION = "mcgill-rem-green";
const baseUrl = "http://api.test";

// Minimal Response stand-in: the client only reads ok, status and json().
function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

/** Run with a fake fetch and return the error it throws. */
async function failure(fetchImpl: typeof fetch): Promise<SimulationRunError> {
  const caught: unknown = await runSimulation(CONNECTION, DEFAULT_RUN_SETTINGS, { baseUrl, fetchImpl })
    .catch((error: unknown) => error);
  expect(caught).toBeInstanceOf(SimulationRunError);
  return caught as SimulationRunError;
}

describe("runSimulation", () => {
  it("posts the settings body to /simulation/run and returns the validated run", async () => {
    const fetchImpl = vi.fn(async () => jsonResponse(200, stationViewData));
    const settings = { strategy: "adaptive", max_hold_time: 45, irregularity_threshold: 0.3 } as const;
    const run = await runSimulation(CONNECTION, settings, { baseUrl, fetchImpl });

    const [url, init] = fetchImpl.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("http://api.test/simulation/run");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body as string)).toStrictEqual({
      connection_id: CONNECTION,
      strategy: "adaptive",
      max_hold_time: 45,
      irregularity_threshold: 0.3,
    });
    expect(run.passengers).toHaveLength(stationViewData.passenger_tracks.length);
  });

  it("explains an unknown connection (404) without the raw API text", async () => {
    const error = await failure(vi.fn(async () =>
      jsonResponse(404, { detail: "Unknown connection: mcgill-rem-green" })));

    expect(error.status).toBe(404);
    expect(error.message).toBe(
      "The simulator does not have this connection. Choose another connection and run again.");
  });

  it("names the rejected field for a 422 validation error", async () => {
    const detail = [
      { loc: ["body", "max_hold_time"], msg: "Input should be a multiple of 5" },
      { loc: ["body"], msg: "Value error, irregularity_threshold is only valid for adaptive" },
    ];
    const error = await failure(vi.fn(async () => jsonResponse(422, { detail })));

    expect(error.status).toBe(422);
    expect(error.message).toBe(
      "The simulator rejected these settings (max_hold_time: Input should be a multiple of 5; "
      + "Value error, irregularity_threshold is only valid for adaptive).");
  });

  it("still explains a 422 whose body has no field list", async () => {
    const error = await failure(vi.fn(async () => new Response("nope", { status: 422 })));

    expect(error.message).toBe(
      "The simulator rejected these settings (check the values and run again).");
  });

  it("hides server details for a 500", async () => {
    const error = await failure(vi.fn(async () =>
      jsonResponse(500, { detail: "Traceback: secret path" })));

    expect(error.message).toBe(
      "The simulation run failed on the server (HTTP 500). Try again in a moment.");
  });

  it("says the API is unreachable when fetch itself fails", async () => {
    const error = await failure(vi.fn(async () => {
      throw new TypeError("Failed to fetch");
    }));

    expect(error.status).toBeNull();
    expect(error.message).toBe(
      "Could not reach the simulation API at http://api.test. Check that the backend is running.");
  });

  it("rethrows an abort unchanged so a cancelled run is not reported as a failure", async () => {
    const controller = new AbortController();
    const abort = new DOMException("Aborted", "AbortError");
    const fetchImpl = vi.fn(async () => {
      controller.abort();
      throw abort;
    });
    const options = { baseUrl, fetchImpl, signal: controller.signal };

    await expect(runSimulation(CONNECTION, DEFAULT_RUN_SETTINGS, options)).rejects.toBe(abort);
  });

  it("rethrows an abort that happens while the response body is being read", async () => {
    const controller = new AbortController();
    const abort = new DOMException("Aborted", "AbortError");
    // The headers arrived; the cancel lands while json() is still reading.
    const response = {
      ok: true,
      status: 200,
      json: async () => {
        controller.abort();
        throw abort;
      },
    } as unknown as Response;
    const fetchImpl = vi.fn(async () => response);
    const options = { baseUrl, fetchImpl, signal: controller.signal };

    await expect(runSimulation(CONNECTION, DEFAULT_RUN_SETTINGS, options)).rejects.toBe(abort);
  });

  it("rejects a response that fails station-view validation", async () => {
    const error = await failure(vi.fn(async () =>
      jsonResponse(200, { ...stationViewData, schema_version: 2 })));

    expect(error.message).toBe("The simulator returned a run the station view cannot display "
      + "(Unsupported station view schema version).");
  });

  it("rejects a run for a different connection", async () => {
    const fetchImpl = vi.fn(async () => jsonResponse(200, stationViewData));
    const result = runSimulation("edouard_montpetit-rem-blue", DEFAULT_RUN_SETTINGS, { baseUrl, fetchImpl });

    await expect(result).rejects.toThrow("Run does not contain connection: edouard_montpetit-rem-blue");
  });
});
