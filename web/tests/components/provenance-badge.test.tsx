// AI contribution: 50% or more AI-generated
// @vitest-environment jsdom
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ProvenanceBadge } from "../../src/components/provenance-badge";

describe("ProvenanceBadge", () => {
  it("renders measured, estimated, published, and assumed labels consistently", () => {
    const { rerender } = render(
      <ProvenanceBadge
        parameterKey="max_hold_time"
        provenance={{ classification: "measured", source_name: "Sensor A", source_link: "" }}
      />,
    );
    expect(screen.getByText("Measured")).toBeTruthy();
    expect(screen.getByText("Sensor A")).toBeTruthy();
    expect(screen.queryByRole("link")).toBeNull();

    rerender(
      <ProvenanceBadge
        parameterKey="max_hold_time"
        provenance={{ classification: "estimated", source_name: "Model B", source_link: "" }}
      />,
    );
    expect(screen.getByText("Estimated")).toBeTruthy();

    rerender(
      <ProvenanceBadge
        parameterKey="max_hold_time"
        provenance={{ classification: "published", source_name: "GTFS", source_link: "https://gtfs.org" }}
      />,
    );
    expect(screen.getByText("Published")).toBeTruthy();
    const link = screen.getByRole("link");
    expect(link.getAttribute("href")).toBe("https://gtfs.org/");
    expect(link.getAttribute("target")).toBe("_blank");

    rerender(
      <ProvenanceBadge
        parameterKey="max_hold_time"
        provenance={{ classification: "assumed", source_name: "Default C", source_link: "" }}
      />,
    );
    expect(screen.getByText("Assumed")).toBeTruthy();
  });

  it("handles missing or invalid provenance gracefully", () => {
    render(<ProvenanceBadge parameterKey="unknown_param" provenance={null} />);
    expect(screen.getByText("Unspecified")).toBeTruthy();
    expect(screen.getByText("Source not specified")).toBeTruthy();
    expect(screen.queryByRole("link")).toBeNull();
  });
});