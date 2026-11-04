// AI contribution: 50% or more AI-generated
/**
 * Pure geometry helpers used by getNetworkSnapshot to move walking passengers
 * along the recorded transfer corridor instead of cutting a straight chord
 * across any bend in its path. No mutable state, no timers.
 */
import type { Point } from "../types/stationView";

interface PolylineProjection {
    point: Point;
    distanceAlongPath: number;
    perpendicularDistance: number;
}

function distance(a: Point, b: Point): number {
    return Math.hypot(b.x - a.x, b.y - a.y);
}

function closestPointOnSegment(
    point: Point,
    a: Point,
    b: Point,
): { point: Point; fraction: number } {
    const dx = b.x - a.x;
    const dy = b.y - a.y;
    const lengthSquared = dx * dx + dy * dy;

    if (lengthSquared === 0) {
        return { point: { ...a }, fraction: 0 };
    }

    const fraction = Math.max(
        0,
        Math.min(
            1,
            ((point.x - a.x) * dx + (point.y - a.y) * dy) /
                lengthSquared,
        ),
    );

    return {
        point: {
            x: a.x + dx * fraction,
            y: a.y + dy * fraction,
        },
        fraction,
    };
}

/**
 * Finds the closest point on the polyline to `point`, returning its
 * perpendicular distance and its arc-length offset from the path start.
 * Returns null for degenerate (fewer than two point) paths.
 */
export function projectOntoPolyline(
    point: Point,
    path: readonly Point[],
): PolylineProjection | null {
    if (path.length < 2) {
        return null;
    }

    let cumulative = 0;
    let best: PolylineProjection | null = null;

    for (let index = 0; index < path.length - 1; index += 1) {
        const a = path[index];
        const b = path[index + 1];
        const segmentLength = distance(a, b);

        const { point: closest, fraction } =
            closestPointOnSegment(point, a, b);

        const perpendicularDistance = distance(point, closest);

        if (
            !best ||
            perpendicularDistance < best.perpendicularDistance
        ) {
            best = {
                point: closest,
                distanceAlongPath:
                    cumulative + fraction * segmentLength,
                perpendicularDistance,
            };
        }

        cumulative += segmentLength;
    }

    return best;
}

/** Converts an arc-length offset back into a coordinate on the polyline. */
function pointAtDistance(
    path: readonly Point[],
    targetDistance: number,
): Point {
    let cumulative = 0;

    for (let index = 0; index < path.length - 1; index += 1) {
        const a = path[index];
        const b = path[index + 1];
        const segmentLength = distance(a, b);
        const isLastSegment = index === path.length - 2;

        if (
            targetDistance <= cumulative + segmentLength ||
            isLastSegment
        ) {
            const remaining = Math.max(
                0,
                Math.min(
                    segmentLength,
                    targetDistance - cumulative,
                ),
            );

            const fraction =
                segmentLength === 0
                    ? 0
                    : remaining / segmentLength;

            return {
                x: a.x + (b.x - a.x) * fraction,
                y: a.y + (b.y - a.y) * fraction,
            };
        }

        cumulative += segmentLength;
    }

    return { ...path[path.length - 1] };
}

// Recorded samples that sit on the corridor land within rounding of it;
// anything further off is an endpoint outside the corridor (e.g. the
// platform approach), where a straight line remains the right fallback.
const ON_PATH_TOLERANCE_PX = 0.5;

/**
 * Interpolates a passenger's position between two recorded samples. When
 * both endpoints lie on the corridor polyline (within tolerance), the
 * returned point follows the polyline's arc length between them, including
 * around any bend. Otherwise this falls back to a direct linear
 * interpolation between the two recorded points.
 */
export function interpolateAlongCorridor(
    from: Point,
    to: Point,
    fraction: number,
    path: readonly Point[] | undefined,
): Point {
    const clampedFraction = Math.max(0, Math.min(1, fraction));

    const linear: Point = {
        x: from.x + (to.x - from.x) * clampedFraction,
        y: from.y + (to.y - from.y) * clampedFraction,
    };

    if (!path || path.length < 2) {
        return linear;
    }

    const fromProjection = projectOntoPolyline(from, path);
    const toProjection = projectOntoPolyline(to, path);

    if (
        !fromProjection ||
        !toProjection ||
        fromProjection.perpendicularDistance > ON_PATH_TOLERANCE_PX ||
        toProjection.perpendicularDistance > ON_PATH_TOLERANCE_PX ||
        toProjection.distanceAlongPath <
            fromProjection.distanceAlongPath
    ) {
        return linear;
    }

    const targetDistance =
        fromProjection.distanceAlongPath +
        (toProjection.distanceAlongPath -
            fromProjection.distanceAlongPath) *
            clampedFraction;

    return pointAtDistance(path, targetDistance);
}
