// AI contribution: 50% or more AI-generated
// @vitest-environment jsdom
/** App loads GET /parameters once and every panel shows each parameter's own source (US-7.1, #311, #313, #314). */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import App from "../../src/App";
import { usePlaybackStore } from "../../src/store/usePlaybackStore";
import type { ParameterProvenanceMap } from "../../src/types/provenance";

/** Settings with different classifications, plus the two schedule feeds with their own links. */
const PROVENANCE: ParameterProvenanceMap = {
  max_hold_time: { classification: "estimated", source_name: "Operational thresholds", source_link: "" },
  strategy: { classification: "assumed", source_name: "Strategy registry", source_link: "" },
  rem_schedule: { classification: "published", source_name: "REM data, CC BY 4.0", source_link: "https://rem.info" },
  stm_schedule: { classification: "published", source_name: "STM data, CC BY 4.0", source_link: "https://www.stm.info" },
};

/** The app with no API except the parameters loader under test. */
function renderApp(parameterProvenanceLoader: () => Promise<ParameterProvenanceMap>) {
  render(
    <App runLoader={null} scenarioRunner={null} connectionCatalogLoader={null}
      parameterProvenanceLoader={parameterProvenanceLoader} />,
  );
}

describe("App parameter provenance", () => {
  beforeEach(() => {
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(null);
    usePlaybackStore.setState({ data: null, selectedConnectionId: null, availableConnections: null });
  });
  afterEach(() => { cleanup(); vi.restoreAllMocks(); });

  it("shows each parameter's own classification and source wherever it appears", async () => {
    const loader = vi.fn().mockResolvedValue(PROVENANCE);
    renderApp(loader);

    // Max hold appears in Run settings and Operating rules, with the same source in both.
    await waitFor(() => expect(screen.getAllByTestId("provenance-max_hold_time")[0].textContent)
      .toContain("Estimated"));
    for (const badge of screen.getAllByTestId("provenance-max_hold_time")) {
      expect(badge.textContent).toBe("EstimatedOperational thresholds");
    }
    expect(screen.getAllByTestId("provenance-max_hold_time")).toHaveLength(2);
    expect(screen.getByTestId("provenance-strategy").textContent).toBe("AssumedStrategy registry");
    // The badge sits outside the legend, so the radio group's name stays "Strategy"
    expect(screen.getByRole("group", { name: "Strategy" })).toBeDefined();
    expect(loader).toHaveBeenCalledTimes(1);
  });

  it("links each schedule feed beside the connection picker to its own data", async () => {
    renderApp(vi.fn().mockResolvedValue(PROVENANCE));

    // Readable names, not raw keys, so screen readers don't say "rem underscore schedule"
    const rem = await screen.findByRole("link", { name: "Source link for REM schedule: REM data, CC BY 4.0" });
    const stm = screen.getByRole("link", { name: "Source link for STM schedule: STM data, CC BY 4.0" });
    expect(rem.getAttribute("href")).toBe("https://rem.info/");
    expect(stm.getAttribute("href")).toBe("https://www.stm.info/");
    expect(screen.getByTestId("provenance-rem_schedule").textContent).toContain("Published");
  });

  it("keeps working and marks sources as unspecified when the request fails", async () => {
    const loader = vi.fn().mockRejectedValue(new Error("HTTP 500"));
    renderApp(loader);

    await waitFor(() => expect(loader).toHaveBeenCalledTimes(1));
    expect(screen.getByTestId("provenance-strategy").textContent).toBe("UnspecifiedSource not specified");
    expect(screen.queryByRole("link", { name: /Source link/ })).toBeNull();
    expect(screen.getByText("Station view")).toBeDefined();
  });
});
