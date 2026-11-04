// AI contribution: 50% or more AI-generated
import { describe, expect, it } from "vitest";
import {
    interpolateAlongCorridor,
    projectOntoPolyline,
} from "../../src/lib/interpolateAlongCorridor";

describe("interpolateAlongCorridor", () => {
    it("interpolates correctly between two recorded points on a straight segment", () => {
        const path = [
            { x: 0, y: 0 },
            { x: 10, y: 0 },
        ];

        const midpoint = interpolateAlongCorridor(
            { x: 0, y: 0 },
            { x: 10, y: 0 },
            0.5,
            path,
        );

        expect(midpoint).toEqual({ x: 5, y: 0 });
    });

    it("follows the corridor polyline around a bend rather than a straight chord", () => {
        // An L-shaped corridor: right along x, then down along y.
        const path = [
            { x: 0, y: 0 },
            { x: 10, y: 0 },
            { x: 10, y: 10 },
        ];

        // Halfway (by arc length) between the two ends sits exactly at the
        // corner, not at the chord's midpoint (5, 5).
        const halfway = interpolateAlongCorridor(
            { x: 0, y: 0 },
            { x: 10, y: 10 },
            0.5,
            path,
        );

        expect(halfway).toEqual({ x: 10, y: 0 });

        // A straight chord would have cut across the corner.
        const chordMidpoint = { x: 5, y: 5 };
        expect(halfway).not.toEqual(chordMidpoint);
    });

    it("interpolates proportionally to arc length along a multi-segment path", () => {
        const path = [
            { x: 0, y: 0 },
            { x: 10, y: 0 },
            { x: 10, y: 10 },
        ];

        // Total arc length is 20; a quarter of the way in is still on the
        // first (horizontal) segment at x = 5.
        const quarter = interpolateAlongCorridor(
            { x: 0, y: 0 },
            { x: 10, y: 10 },
            0.25,
            path,
        );

        expect(quarter).toEqual({ x: 5, y: 0 });
    });

    it("falls back to a direct line when an endpoint is off the corridor", () => {
        const path = [
            { x: 0, y: 0 },
            { x: 10, y: 0 },
        ];

        // (5, 50) is far from the path, so this should not be treated as
        // on-corridor movement.
        const result = interpolateAlongCorridor(
            { x: 0, y: 0 },
            { x: 5, y: 50 },
            0.5,
            path,
        );

        expect(result).toEqual({ x: 2.5, y: 25 });
    });

    it("falls back to a direct line when no corridor path is supplied", () => {
        const result = interpolateAlongCorridor(
            { x: 0, y: 0 },
            { x: 10, y: 10 },
            0.5,
            undefined,
        );

        expect(result).toEqual({ x: 5, y: 5 });
    });

    it("clamps the fraction to [0, 1]", () => {
        const path = [
            { x: 0, y: 0 },
            { x: 10, y: 0 },
        ];

        expect(
            interpolateAlongCorridor(
                { x: 0, y: 0 },
                { x: 10, y: 0 },
                -1,
                path,
            ),
        ).toEqual({ x: 0, y: 0 });

        expect(
            interpolateAlongCorridor(
                { x: 0, y: 0 },
                { x: 10, y: 0 },
                2,
                path,
            ),
        ).toEqual({ x: 10, y: 0 });
    });
});

describe("projectOntoPolyline", () => {
    it("returns null for a degenerate (single-point) path", () => {
        expect(projectOntoPolyline({ x: 0, y: 0 }, [{ x: 0, y: 0 }])).toBeNull();
    });

    it("finds the nearest point and arc-length offset on a bent path", () => {
        const path = [
            { x: 0, y: 0 },
            { x: 10, y: 0 },
            { x: 10, y: 10 },
        ];

        const projection = projectOntoPolyline({ x: 10, y: 4 }, path);

        expect(projection).not.toBeNull();
        expect(projection?.perpendicularDistance).toBeCloseTo(0);
        expect(projection?.distanceAlongPath).toBeCloseTo(14);
    });
});
