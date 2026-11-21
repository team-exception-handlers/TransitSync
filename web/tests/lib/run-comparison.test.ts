// AI contribution: 50% or more AI-generated
/** runComparison posts the panel's settings and checks both runs (US-4.1, #230). */
import { describe, expect, it, vi } from "vitest";
import { stationViewData } from "../../src/data/stationViewData";
import { DEFAULT_RUN_SETTINGS } from "../../src/lib/run-settings";
import {
  SimulationRunError,
  parseSimulationComparison,
  runComparison,
} from "../../src/lib/simulation-api";

const CONNECTION = "mcgill-rem-green";
const baseUrl = "http://api.test";

// The API's comparison body: both sides plus the shared starting conditions.
const BODY = {
  holding: stationViewData,
  no_holding: stationViewData,
  holding_strategy: "connection_protection",
  service_date: "2026-10-05",
  master_seed: 42,
  duration_s: stationViewData.duration_s,
};

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

/** Compare with a fake fetch and return the error it throws. */
async function failure(fetchImpl: typeof fetch): Promise<SimulationRunError> {
  const caught: unknown = await runComparison(CONNECTION, DEFAULT_RUN_SETTINGS, { baseUrl, fetchImpl })
    .catch((error: unknown) => error);
  expect(caught).toBeInstanceOf(SimulationRunError);
  return caught as SimulationRunError;
}

describe("runComparison", () => {
  it("posts the settings body to /simulation/comparison and returns both runs", async () => {
    const fetchImpl = vi.fn(async () => jsonResponse(200, BODY));
    const settings = { ...DEFAULT_RUN_SETTINGS, strategy: "connection_protection" as const, max_hold_time: 60 };

    const pair = await runComparison(CONNECTION, settings, { baseUrl, fetchImpl });

    const [url, init] = fetchImpl.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("http://api.test/simulation/comparison");
    expect(init.method).toBe("POST");
    const sent = JSON.parse(init.body as string) as Record<string, unknown>;
    expect(sent).toMatchObject({ connection_id: CONNECTION, strategy: "connection_protection", max_hold_time: 60 });
    expect(pair.holdingStrategy).toBe("connection_protection");
    expect(pair.startingConditions).toEqual({ serviceDate: "2026-10-05", masterSeed: 42, duration_s: 360 });
    expect(pair.holding.connections.map((item) => item.id)).toContain(CONNECTION);
    expect(pair.noHolding.duration_s).toBe(360);
  });

  it("explains an unknown connection (404)", async () => {
    const error = await failure(vi.fn(async () => jsonResponse(404, { detail: "Unknown connection: x" })));
    expect(error.status).toBe(404);
    expect(error.message).toContain("does not have this connection");
  });

  it("names the rejected field (422)", async () => {
    const detail = [{ loc: ["body", "max_hold_time"], msg: "Input should be less than or equal to 300" }];
    const error = await failure(vi.fn(async () => jsonResponse(422, { detail })));
    expect(error.message).toBe(
      "The simulator rejected these settings (max_hold_time: Input should be less than or equal to 300).");
  });

  it("hides server details on a 500", async () => {
    const error = await failure(vi.fn(async () => jsonResponse(500, { detail: "Simulation comparison failed" })));
    expect(error.message).toContain("failed on the server (HTTP 500)");
  });

  it("rejects a body the Compare screen cannot show", async () => {
    const error = await failure(vi.fn(async () => jsonResponse(200, { ...BODY, master_seed: -1 })));
    expect(error.message).toContain("Invalid comparison master seed");
  });
});

describe("parseSimulationComparison", () => {
  it.each([
    [{ ...BODY, service_date: "05/10/2026" }, "Invalid comparison service date"],
    [{ ...BODY, holding_strategy: "" }, "Invalid comparison holding strategy"],
    [{ ...BODY, duration_s: 0 }, "Invalid comparison duration"],
    [{ ...BODY, duration_s: 3600 }, "Comparison runs do not share one duration"],
    ["not an object", "Comparison response must be an object"],
  ])("rejects %#", (body, message) => {
    expect(() => parseSimulationComparison(body, CONNECTION)).toThrow(message);
  });

  it("rejects a side that is missing the requested connection", () => {
    expect(() => parseSimulationComparison(BODY, "edouard_montpetit-rem-blue"))
      .toThrow("Run does not contain connection: edouard_montpetit-rem-blue");
  });
});
