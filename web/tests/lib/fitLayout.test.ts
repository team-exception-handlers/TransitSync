// AI contribution: 50% or more AI-generated
import { describe, expect, it } from "vitest";
import { fitLayout } from "../../src/lib/fitLayout";

describe("fitLayout", () => {
  const map = { width: 800, height: 600 };

  it("fills a view with the same aspect ratio with no letterbox", () => {
    const result = fitLayout(map, { width: 1600, height: 1200 });

    expect(result.scale).toBe(2);
    expect(result.offsetX).toBe(0);
    expect(result.offsetY).toBe(0);
    expect(result.renderWidth).toBe(1600);
    expect(result.renderHeight).toBe(1200);
  });

  it("letterboxes a view narrower than the fixture's aspect ratio (pillarbox top/bottom removed, bars on the sides)", () => {
    // view is wider relative to its height than the map, so height is the
    // binding constraint and horizontal bars appear on the sides.
    const result = fitLayout(map, { width: 2000, height: 600 });

    expect(result.scale).toBe(1);
    expect(result.offsetY).toBe(0);
    expect(result.offsetX).toBeCloseTo((2000 - 800) / 2);
    expect(result.renderWidth).toBe(800);
    expect(result.renderHeight).toBe(600);
  });

  it("letterboxes a view taller than the fixture's aspect ratio (bars on top/bottom)", () => {
    const result = fitLayout(map, { width: 400, height: 1200 });

    // width is the binding constraint: scale = 400/800 = 0.5
    expect(result.scale).toBe(0.5);
    expect(result.renderWidth).toBe(400);
    expect(result.renderHeight).toBe(300);
    expect(result.offsetX).toBe(0);
    expect(result.offsetY).toBeCloseTo((1200 - 300) / 2);
  });

  it("scales down to fit a smaller view box", () => {
    const result = fitLayout(map, { width: 400, height: 300 });

    expect(result.scale).toBe(0.5);
    expect(result.renderWidth).toBe(400);
    expect(result.renderHeight).toBe(300);
    expect(result.offsetX).toBe(0);
    expect(result.offsetY).toBe(0);
  });

  it("centres the scaled render inside a much larger square view", () => {
    const result = fitLayout(map, { width: 1000, height: 1000 });

    // width is binding: scale = min(1000/800, 1000/600) = 1.25
    const expectedScale = 1000 / 800;
    expect(result.scale).toBeCloseTo(expectedScale);
    expect(result.renderWidth).toBeCloseTo(1000);
    expect(result.renderHeight).toBeCloseTo(600 * expectedScale);
    expect(result.offsetX).toBeCloseTo(0);
    expect(result.offsetY).toBeGreaterThan(0);
  });

  it("falls back to an untranslated identity fit for a degenerate view box", () => {
    const result = fitLayout(map, { width: 0, height: 0 });

    expect(result.scale).toBe(1);
    expect(result.offsetX).toBe(0);
    expect(result.offsetY).toBe(0);
  });

  it("falls back to an untranslated identity fit for a degenerate map box", () => {
    const result = fitLayout({ width: 0, height: 600 }, { width: 400, height: 300 });

    expect(result.scale).toBe(1);
    expect(result.offsetX).toBe(0);
    expect(result.offsetY).toBe(0);
  });
});
