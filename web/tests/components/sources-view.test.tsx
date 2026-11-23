// AI contribution: 50% or more AI-generated
// @vitest-environment jsdom
/** Sources screen: opened from the sidebar and Run settings, with the run's values (#320). */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import App from "../../src/App";
import { SourcesView } from "../../src/components/sources-view";
import { runValues } from "../../src/lib/parameter-sources";
import { DEFAULT_RUN_SETTINGS } from "../../src/lib/run-settings";
import { usePlaybackStore } from "../../src/store/usePlaybackStore";
import { useRunSettingsStore } from "../../src/store/useRunSettingsStore";
import { useViewStore } from "../../src/store/useViewStore";
import type { ParameterProvenanceMap } from "../../src/types/provenance";

const PROVENANCE: ParameterProvenanceMap = {
  max_hold_time: { classification: "estimated", source_name: "Operational thresholds", source_link: "" },
  strategy: { classification: "assumed", source_name: "Strategy registry", source_link: "" },
};

/** The table row whose header cell is `label`. */
function rowOf(label: string) {
  return within(screen.getByRole("rowheader", { name: label }).closest("tr") as HTMLElement);
}

beforeEach(() => {
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(null);
  usePlaybackStore.setState({
    data: null, selectedConnectionId: null, availableConnections: null, simulatedConnectionIds: [],
  });
  useRunSettingsStore.setState({ applied: {} });
  // The sidebar screen is global state, so each test starts on the station view.
  useViewStore.setState({ activeView: "station" });
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); });

describe("Opening the Sources screen", () => {
  function renderApp() {
    render(<App runLoader={null} scenarioRunner={null} connectionCatalogLoader={null}
      parameterProvenanceLoader={vi.fn().mockResolvedValue(PROVENANCE)} />);
  }

  it("switches from the station view to Sources and back from the sidebar", async () => {
    renderApp();
    const nav = within(screen.getByRole("navigation", { name: "Workspace" }));

    fireEvent.click(nav.getByRole("button", { name: "Sources" }));
    expect(await screen.findByRole("rowheader", { name: "Maximum hold" })).toBeDefined();
    expect(nav.getByRole("button", { name: "Sources" }).getAttribute("aria-current")).toBe("page");
    expect(screen.queryByRole("region", { name: "Station view" })).toBeNull();

    fireEvent.click(nav.getByRole("button", { name: "Station view" }));
    expect(screen.getByRole("region", { name: "Station view" })).toBeDefined();
  });

  it("opens Sources from the link in Run settings", async () => {
    renderApp();
    // Run settings live on Scenario setup since #408, not on the station view.
    fireEvent.click(within(screen.getByRole("navigation", { name: "Workspace" }))
      .getByRole("button", { name: "Scenario setup" }));

    fireEvent.click(screen.getByRole("button", { name: "Where these values come from" }));

    expect(await screen.findByRole("heading", { name: "Where each value comes from" })).toBeDefined();
  });
});

describe("SourcesView", () => {
  it("shows the values the selected connection's run used beside their sources", () => {
    usePlaybackStore.setState({ selectedConnectionId: "mcgill", simulatedConnectionIds: ["mcgill"] });
    useRunSettingsStore.setState({ applied: { mcgill: { ...DEFAULT_RUN_SETTINGS, max_hold_time: 120 } } });
    render(<SourcesView provenance={PROVENANCE} />);

    expect(rowOf("Maximum hold").getByText("120 s")).toBeDefined();
    expect(rowOf("Maximum hold").getByText("Operational thresholds")).toBeDefined();
    expect(rowOf("Strategy").getByText("No control")).toBeDefined();
    // A run value with no backend entry still gets a row, marked as unsourced
    expect(rowOf("Passenger flow").getByText("No source recorded yet")).toBeDefined();
  });

  it("marks inputs every run uses but Run settings cannot change as fixed, not blank", () => {
    usePlaybackStore.setState({ selectedConnectionId: "mcgill", simulatedConnectionIds: ["mcgill"] });
    render(<SourcesView provenance={{
      ...PROVENANCE,
      min_safe_gap: { classification: "assumed", source_name: "Operational thresholds", source_link: "" },
    }} />);

    expect(rowOf("min_safe_gap").getByText("Fixed value")).toBeDefined();
    expect(screen.getByText(/Fixed value means the run used the simulator's own value/)).toBeDefined();
    // A real run value is still shown as the value, not as fixed
    expect(rowOf("Maximum hold").queryByText("Fixed value")).toBeNull();
  });

  it("uses the API defaults for a run loaded without Run scenario", () => {
    usePlaybackStore.setState({ selectedConnectionId: "mcgill", simulatedConnectionIds: ["mcgill"] });
    render(<SourcesView provenance={PROVENANCE} />);

    expect(rowOf("Maximum hold").getByText("300 s")).toBeDefined();
  });

  it("shows no values for mock playback", () => {
    usePlaybackStore.setState({ selectedConnectionId: "mcgill" });
    render(<SourcesView provenance={PROVENANCE} />);

    expect(screen.getByText(/Mock playback uses no run settings/)).toBeDefined();
    expect(rowOf("Maximum hold").getByText("—")).toBeDefined();
    expect(screen.queryByRole("rowheader", { name: "Passenger flow" })).toBeNull();
  });

  it("says so when no sources could be loaded", () => {
    render(<SourcesView provenance={{}} />);

    expect(screen.getByText("No sources could be loaded from the simulation API.")).toBeDefined();
  });
});

describe("runValues", () => {
  it("only gives the threshold a value when the strategy is Adaptive", () => {
    expect(runValues(DEFAULT_RUN_SETTINGS).irregularity_threshold).toBe("Not used by this strategy");
    expect(runValues({ ...DEFAULT_RUN_SETTINGS, strategy: "adaptive" }).irregularity_threshold).toBe("0.25");
  });

  it("shows kappa as the error magnitude, since the API uses one as the other", () => {
    const values = runValues({ ...DEFAULT_RUN_SETTINGS, error_magnitude: 1.5 });
    expect(values.kappa).toBe(values.error_magnitude);
    expect(values.kappa).toBe("1.5");
  });

  it("shows the disruption preset with its start and size", () => {
    expect(runValues(DEFAULT_RUN_SETTINGS).disruption_enabled).toBe("None");
    const suspended = { ...DEFAULT_RUN_SETTINGS, disruption_preset: "line_suspension" as const,
      disruption_time_s: 300, disruption_magnitude: 180 };
    expect(runValues(suspended).disruption_enabled).toBe("Line suspension at 300 s, 180 s");
  });
});
