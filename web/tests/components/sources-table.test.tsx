// AI contribution: 50% or more AI-generated
// @vitest-environment jsdom
/** Sources table: rows, label filter, details with link, missing source (#319, #321). */
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { SourcesTable } from "../../src/components/sources-table";
import type { SourceRow } from "../../src/lib/parameter-sources";

const rows: SourceRow[] = [
  {
    name: "connection_id", label: "connection_id", value: null, classification: "published",
    sourceName: "GTFS schedule", sourceLink: "https://gtfs.org/",
  },
  {
    name: "max_hold_time", label: "Maximum hold", value: "120 s", classification: "estimated",
    sourceName: "Operational thresholds", sourceLink: "",
  },
  {
    name: "transfer_volume", label: "Transfer volume", value: "80 passengers",
    classification: null, sourceName: null, sourceLink: null,
  },
];

/** The table row whose header cell is `label`. */
function rowOf(label: string): HTMLElement {
  return screen.getByRole("rowheader", { name: label }).closest("tr") as HTMLElement;
}

describe("SourcesTable", () => {
  afterEach(cleanup);

  it("shows each input with its own value, label and source", () => {
    render(<SourcesTable rows={rows} />);

    const hold = within(rowOf("Maximum hold"));
    expect(hold.getByText("120 s")).toBeDefined();
    expect(hold.getByText("Estimated")).toBeDefined();
    expect(hold.getByText("Operational thresholds")).toBeDefined();
    expect(within(rowOf("connection_id")).getByText("GTFS schedule")).toBeDefined();
  });

  it("marks an input with no recorded source", () => {
    render(<SourcesTable rows={rows} />);

    const flow = rowOf("Transfer volume");
    expect(within(flow).getByText("No source recorded yet").className).toBe("source-missing");
  });

  it("filters by label and counts each label", () => {
    render(<SourcesTable rows={rows} />);

    fireEvent.click(screen.getByRole("button", { name: "Published · 1" }));
    expect(screen.getByRole("rowheader", { name: "connection_id" })).toBeDefined();
    expect(screen.queryByRole("rowheader", { name: "Maximum hold" })).toBeNull();
    expect(screen.queryByRole("rowheader", { name: "Transfer volume" })).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Measured · 0" }));
    expect(screen.getByText("No inputs have this label.")).toBeDefined();
  });

  it("opens a row to show the label meaning and the source link", () => {
    render(<SourcesTable rows={rows} />);

    const toggle = screen.getByRole("button", { name: "Details for connection_id" });
    fireEvent.click(toggle);

    expect(toggle.getAttribute("aria-expanded")).toBe("true");
    expect(screen.getByText(/^Published: Taken from STM or REM data/)).toBeDefined();
    expect(screen.getByRole("link", { name: "https://gtfs.org/" }).getAttribute("href")).toBe("https://gtfs.org/");
  });

  it("does not link an unsafe source URL", () => {
    const unsafe = [{ ...rows[1], sourceLink: "javascript:alert(1)" }];
    render(<SourcesTable rows={unsafe} />);

    fireEvent.click(screen.getByRole("button", { name: "Details for Maximum hold" }));

    expect(screen.queryByRole("link")).toBeNull();
    expect(screen.getByText("None yet")).toBeDefined();
  });

  it("says there is no link or source yet when none is recorded", () => {
    render(<SourcesTable rows={rows} />);

    fireEvent.click(screen.getByRole("button", { name: "Details for Transfer volume" }));

    expect(screen.getByText("None yet")).toBeDefined();
    expect(screen.getByText("No label recorded yet")).toBeDefined();
    expect(screen.queryByRole("link")).toBeNull();
  });
});
