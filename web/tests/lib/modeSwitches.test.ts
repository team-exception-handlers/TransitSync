// AI contribution: 50% or more AI-generated
/** Mode-switch records become timeline markers at the right fraction (#60). */
import { describe, expect, it } from "vitest";
import { KIND_MODE_SWITCH, modeLabel, modeSwitchMarkers } from "../../src/lib/modeSwitches";

// Shape written by DecisionAuditLog.record_mode_switch in the simulator.
function switchRecord(time_s: number, to_mode = "headway_regulation") {
  return {
    schema_version: 2,
    kind: KIND_MODE_SWITCH,
    strategy: "adaptive",
    time_s,
    train_id: "T1",
    station_id: "S1",
    platform_id: "green_mcgill_0",
    line_id: "green",
    from_mode: to_mode === "headway_regulation" ? "connection_protection" : "headway_regulation",
    to_mode,
    service_irregularity: 0.31,
    irregularity_threshold: 0.25,
  };
}

// The simulator declares the kind once; this checks the front end's copy of it.
const auditSource = Object.values(import.meta.glob<string>(
  "../../../simulator/control/decision_audit.py", { query: "?raw", import: "default", eager: true }))[0];

describe("modeSwitchMarkers", () => {
  it("uses the simulator's mode-switch kind", () => {
    expect(auditSource).toContain(`KIND_MODE_SWITCH = "${KIND_MODE_SWITCH}"`);
  });

  it.each([
    [0, 0],
    [900, 0.25],
    [1800, 0.5],
    [3600, 1],
  ])("places a switch at %d s of a 3600 s run at fraction %d", (time_s, fraction) => {
    const [marker] = modeSwitchMarkers({ duration_s: 3600, decisions: [switchRecord(time_s)] });

    expect(marker.fraction).toBe(fraction);
    expect(marker.time_s).toBe(time_s);
  });

  it("keeps both directions of a switch, in time order", () => {
    const decisions = [switchRecord(2700, "connection_protection"), switchRecord(900)];
    const markers = modeSwitchMarkers({ duration_s: 3600, decisions });

    expect(markers.map((marker) => marker.time_s)).toStrictEqual([900, 2700]);
    expect(markers[0].to_mode).toBe("headway_regulation");
    expect(markers[1].from_mode).toBe("headway_regulation");
    expect(markers[1].to_mode).toBe("connection_protection");
  });

  it("gives switches at the same time on different platforms distinct ids", () => {
    const other = { ...switchRecord(900), platform_id: "green_mcgill_1" };
    const markers = modeSwitchMarkers({ duration_s: 3600, decisions: [switchRecord(900), other] });

    expect(new Set(markers.map((marker) => marker.id)).size).toBe(2);
  });

  it("returns no markers when the run has no switch entries", () => {
    const hold = { time_s: 120, train_id: "T1", requested_s: 30, applied_s: 30, reason: "hold" };
    const search = { ...switchRecord(300), kind: "hold_search" };

    expect(modeSwitchMarkers({ duration_s: 3600, decisions: [hold, search] })).toStrictEqual([]);
    expect(modeSwitchMarkers({ duration_s: 3600, decisions: [] })).toStrictEqual([]);
    expect(modeSwitchMarkers({ duration_s: 3600 })).toStrictEqual([]);
    expect(modeSwitchMarkers(null)).toStrictEqual([]);
  });

  it("skips malformed records and switches outside the run", () => {
    const decisions = [
      null,
      "mode_switch",
      { ...switchRecord(100), time_s: "100" },
      { ...switchRecord(100), to_mode: undefined },
      switchRecord(-1),
      switchRecord(3601),
      switchRecord(Number.NaN),
    ];

    expect(modeSwitchMarkers({ duration_s: 3600, decisions })).toStrictEqual([]);
  });

  it("returns no markers for a run without a positive duration", () => {
    expect(modeSwitchMarkers({ duration_s: 0, decisions: [switchRecord(0)] })).toStrictEqual([]);
  });
});

describe("modeLabel", () => {
  it("turns a strategy name into words", () => {
    expect(modeLabel("connection_protection")).toBe("connection protection");
  });
});
