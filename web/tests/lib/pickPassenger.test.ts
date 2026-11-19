// AI contribution: 50% or more AI-generated
import { describe, expect, it } from "vitest";
import { PICK_RADIUS_PX, pickPassenger } from "../../src/lib/pickPassenger";

import type { PassengerPosition } from "../../src/types/stationView";

function marker(id: string, x: number, y: number): PassengerPosition {
  return {
    passenger_id: id,
    group_id: "g-1",
    connection_id: "conn-1",
    position: { x, y },
    phase: "walking",
  };
}

const UNSCALED = { scale: 1, offsetX: 0, offsetY: 0 };

describe("pickPassenger", () => {
  it("picks the marker under the click when the map is drawn unscaled", () => {
    const markers = [marker("p-001", 389, 135), marker("p-002", 405, 310)];

    expect(pickPassenger(markers, { x: 390, y: 136 }, UNSCALED)).toBe("p-001");
  });

  it("undoes the fit scale and letterbox offset before matching", () => {
    // Map (200, 100) drawn at scale 0.5 with a 100 px left offset lands on screen (200, 50).
    const fit = { scale: 0.5, offsetX: 100, offsetY: 0 };

    expect(pickPassenger([marker("p-001", 200, 100)], { x: 200, y: 50 }, fit)).toBe("p-001");
    // 7 screen px away is 14 map px, still inside the 8 px pick radius once scaled.
    expect(pickPassenger([marker("p-001", 200, 100)], { x: 207, y: 50 }, fit)).toBe("p-001");
  });

  it("picks at exactly the pick radius but not one pixel past it", () => {
    const markers = [marker("p-001", 100, 100)];

    expect(pickPassenger(markers, { x: 100 + PICK_RADIUS_PX, y: 100 }, UNSCALED)).toBe("p-001");
    expect(pickPassenger(markers, { x: 101 + PICK_RADIUS_PX, y: 100 }, UNSCALED)).toBeNull();
  });

  it("picks the nearest of two overlapping markers, and the lower ID on a tie", () => {
    const near = marker("p-009", 102, 100);
    const far = marker("p-001", 95, 100);
    expect(pickPassenger([far, near], { x: 101, y: 100 }, UNSCALED)).toBe("p-009");

    const left = marker("p-002", 98, 100);
    const right = marker("p-001", 102, 100);
    expect(pickPassenger([left, right], { x: 100, y: 100 }, UNSCALED)).toBe("p-001");
  });

  it("returns null when there are no markers to pick", () => {
    expect(pickPassenger([], { x: 100, y: 100 }, UNSCALED)).toBeNull();
  });
});
