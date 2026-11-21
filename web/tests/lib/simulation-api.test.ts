// AI contribution: 50% or more AI-generated
/** The run client sends the selected connection and rejects unusable responses (#79). */
import { describe, expect, it, vi } from "vitest";
import { stationViewData } from "../../src/data/stationViewData";
import {
  SimulationRunError,
  configuredApiUrl,
  createConnectionCatalogLoader,
  createConnectionRunLoader,
  parseConnectionSummaries,
  createParameterProvenanceLoader, 
  parseParameterProvenance
} from "../../src/lib/simulation-api";

// Minimal Response stand-in: the client only reads ok, status and json().
function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("configuredApiUrl", () => {
  it("treats a missing or blank URL as mock-only mode", () => {
    expect(configuredApiUrl(undefined)).toBeNull();
    expect(configuredApiUrl("   ")).toBeNull();
  });

  it("drops trailing slashes so the endpoint path joins cleanly", () => {
    expect(configuredApiUrl(" http://localhost:8000// ")).toBe("http://localhost:8000");
  });
});

describe("createConnectionRunLoader", () => {
  it("posts the connection ID to /simulation/run and returns the validated run", async () => {
    const fetchImpl = vi.fn(async () => jsonResponse(200, stationViewData));
    const run = await createConnectionRunLoader("http://api.test", fetchImpl)("mcgill-rem-green");

    expect(fetchImpl).toHaveBeenCalledTimes(1);
    const [url, init] = fetchImpl.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("http://api.test/simulation/run");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body as string)).toStrictEqual({ connection_id: "mcgill-rem-green" });
    expect(run.interchange.id).toBe("mcgill");
    // Passenger movements are derived by the validator, not sent by the API.
    expect(run.passengers).toHaveLength(stationViewData.passenger_tracks.length);
  });

  it("passes the abort signal through to fetch", async () => {
    const fetchImpl = vi.fn(async () => jsonResponse(200, stationViewData));
    const controller = new AbortController();
    await createConnectionRunLoader("http://api.test", fetchImpl)("mcgill-rem-green", controller.signal);

    const init = (fetchImpl.mock.calls[0] as unknown as [string, RequestInit])[1];
    expect(init.signal).toBe(controller.signal);
  });

  it("reports an unknown connection with the API's 404 detail", async () => {
    const fetchImpl = vi.fn(async () => jsonResponse(404, { detail: "Unknown connection: nowhere" }));
    const error = await createConnectionRunLoader("http://api.test", fetchImpl)("nowhere")
      .catch((caught: unknown) => caught);

    expect(error).toBeInstanceOf(SimulationRunError);
    expect((error as SimulationRunError).status).toBe(404);
    expect((error as SimulationRunError).message).toBe("Unknown connection: nowhere");
  });

  it("falls back to the HTTP status when the error body is not JSON", async () => {
    const fetchImpl = vi.fn(async () => new Response("<html>bad gateway</html>", { status: 502 }));
    await expect(createConnectionRunLoader("http://api.test", fetchImpl)("mcgill-rem-green"))
      .rejects.toThrow("Simulation run failed (HTTP 502)");
  });

  it("does not show a 422 field-error list as the message", async () => {
    const fetchImpl = vi.fn(async () => jsonResponse(422, { detail: [{ loc: ["body"], msg: "bad" }] }));
    await expect(createConnectionRunLoader("http://api.test", fetchImpl)("mcgill-rem-green"))
      .rejects.toThrow("Simulation run failed (HTTP 422)");
  });

  it("rejects a response that fails station-view validation", async () => {
    const fetchImpl = vi.fn(async () => jsonResponse(200, { ...stationViewData, schema_version: 2 }));
    await expect(createConnectionRunLoader("http://api.test", fetchImpl)("mcgill-rem-green"))
      .rejects.toThrow("Unsupported station view schema version");
  });

  it("rejects a valid run that does not contain the requested connection", async () => {
    const fetchImpl = vi.fn(async () => jsonResponse(200, stationViewData));
    await expect(createConnectionRunLoader("http://api.test", fetchImpl)("edouard_montpetit-rem-blue"))
      .rejects.toThrow("Run does not contain connection: edouard_montpetit-rem-blue");
  });
});

// The backend's connection catalog, used to populate the selector (#76).
const CONNECTION_CATALOG = [
  {
    id: "gare_centrale_bonaventure-rem-orange",
    label: "Gare Centrale ↔ Bonaventure",
    metro_line_id: "orange",
    interchange: { id: "gare_centrale_bonaventure", name: "Gare Centrale ↔ Bonaventure" },
  },
  {
    id: "mcgill-rem-green",
    label: "McGill",
    metro_line_id: "green",
    interchange: { id: "mcgill", name: "McGill" },
  },
  {
    id: "edouard_montpetit-rem-blue",
    label: "Édouard-Montpetit",
    metro_line_id: "blue",
    interchange: { id: "edouard_montpetit", name: "Édouard-Montpetit" },
  },
];

describe("parseConnectionSummaries", () => {
  it("accepts the three documented connections with their metro line", () => {
    expect(parseConnectionSummaries(CONNECTION_CATALOG)).toStrictEqual(CONNECTION_CATALOG);
  });

  it("rejects a response that is not an array", () => {
    expect(() => parseConnectionSummaries({ id: "mcgill-rem-green" }))
      .toThrow("Connection list response is not an array");
  });

  it("rejects an entry missing a required field", () => {
    const missingLabel = [{ ...CONNECTION_CATALOG[1], label: "" }];
    expect(() => parseConnectionSummaries(missingLabel))
      .toThrow("Invalid connection summary in catalog response");
  });

  it("rejects an entry naming an unknown metro line", () => {
    const badLine = [{ ...CONNECTION_CATALOG[1], metro_line_id: "purple" }];
    expect(() => parseConnectionSummaries(badLine))
      .toThrow("Invalid connection summary in catalog response");
  });

  it("rejects an entry with an incomplete interchange", () => {
    const badInterchange = [{ ...CONNECTION_CATALOG[1], interchange: { id: "mcgill" } }];
    expect(() => parseConnectionSummaries(badInterchange))
      .toThrow("Invalid connection summary in catalog response");
  });
});

describe("createConnectionCatalogLoader", () => {
  it("GETs /connections and returns the validated catalog", async () => {
    const fetchImpl = vi.fn(async () => jsonResponse(200, CONNECTION_CATALOG));
    const catalog = await createConnectionCatalogLoader("http://api.test", fetchImpl)();

    expect(fetchImpl).toHaveBeenCalledTimes(1);
    const [url] = fetchImpl.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("http://api.test/connections");
    expect(catalog).toStrictEqual(CONNECTION_CATALOG);
  });

  it("passes the abort signal through to fetch", async () => {
    const fetchImpl = vi.fn(async () => jsonResponse(200, CONNECTION_CATALOG));
    const controller = new AbortController();
    await createConnectionCatalogLoader("http://api.test", fetchImpl)(controller.signal);

    const init = (fetchImpl.mock.calls[0] as unknown as [string, RequestInit])[1];
    expect(init.signal).toBe(controller.signal);
  });

  it("reports an HTTP failure with the status code", async () => {
    const fetchImpl = vi.fn(async () => new Response("server error", { status: 500 }));
    const error = await createConnectionCatalogLoader("http://api.test", fetchImpl)()
      .catch((caught: unknown) => caught);

    expect(error).toBeInstanceOf(SimulationRunError);
    expect((error as SimulationRunError).status).toBe(500);
    expect((error as SimulationRunError).message).toBe(
      "Could not load the connection list (HTTP 500).",
    );
  });

  it("rejects a response with an invalid connection summary", async () => {
    const fetchImpl = vi.fn(async () => jsonResponse(200, [{ id: "x" }]));
    await expect(createConnectionCatalogLoader("http://api.test", fetchImpl)())
      .rejects.toThrow("Invalid connection summary in catalog response");
  });
});

describe("parameter provenance loader", () => {
  it("parses and normalizes /parameters response", async () => {
    const mockFetch = async () =>
      new Response(
        JSON.stringify({
          max_hold_time: {
            classification: "estimated",
            source_name: "Operational Thresholds",
            source_link: "https://example.com/docs",
          },
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      );

    const load = createParameterProvenanceLoader("http://localhost:8000", mockFetch as typeof fetch);
    const map = await load();
    expect(map.max_hold_time?.classification).toBe("estimated");
    expect(map.max_hold_time?.source_name).toBe("Operational Thresholds");
  });

  it("rejects non-object provenance payloads", () => {
    expect(() => parseParameterProvenance([])).toThrow();
  });
});
