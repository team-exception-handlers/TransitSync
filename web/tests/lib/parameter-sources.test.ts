// AI contribution: 50% or more AI-generated
/** Building Sources table rows from the provenance map (#319, #321). */
import { describe, expect, it } from "vitest";
import { buildSourceRows } from "../../src/lib/parameter-sources";

const gtfs = {
  classification: "published" as const,
  source_name: "TransitSync GTFS Network Schedule",
  source_link: "https://developers.google.com/transit/gtfs",
};
const hold = { classification: "estimated" as const, source_name: "TransitSync Operational Thresholds", source_link: "" };

describe("buildSourceRows", () => {
  it("pairs each value with its own source and labels run settings", () => {
    const rows = buildSourceRows({ connection_id: gtfs, max_hold_time: hold }, { max_hold_time: "120 s" });

    expect(rows).toEqual([
      {
        name: "connection_id", label: "connection_id", value: null, classification: "published",
        sourceName: gtfs.source_name, sourceLink: gtfs.source_link,
      },
      {
        name: "max_hold_time", label: "Maximum hold", value: "120 s", classification: "estimated",
        sourceName: hold.source_name, sourceLink: "",
      },
    ]);
  });

  it("adds a row with no source for a value the backend does not list", () => {
    const rows = buildSourceRows({}, { transfer_volume: "80 passengers" });

    expect(rows).toEqual([{
      name: "transfer_volume", label: "Transfer volume", value: "80 passengers",
      classification: null, sourceName: null, sourceLink: null,
    }]);
  });

  it("treats a blank source name and an invalid label as not recorded", () => {
    const [row] = buildSourceRows({ strategy: { classification: null, source_name: "   " } });

    expect(row.classification).toBeNull();
    expect(row.sourceName).toBeNull();
  });
});
