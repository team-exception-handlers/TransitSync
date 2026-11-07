// AI contribution: 50% or more AI-generated
/**
 * Deterministic passenger marker sampling for the station canvas.
 *
 * When a connection has more passengers than the canvas can legibly draw,
 * this picks a stable subset instead of drawing every marker. Selection is
 * keyed off a hash of each passenger_id, never array order, index or wall
 * time, so:
 *  - the same input always produces the identical subset (determinism), and
 *  - a passenger entering or leaving the station only ever changes its own
 *    membership plus (at most) one boundary passenger, rather than
 *    reshuffling the whole sample frame to frame.
 *
 * The true passenger count is always returned alongside the sample so the
 * caller can label it, independent of how many markers were actually drawn.
 */
import type { PassengerPosition } from "../types/stationView";

export interface PassengerSampleResult {
    /** Stable subset of passengers to draw a marker for, sorted by passenger_id. */
    sampled: PassengerPosition[];
    /** Total passengers in the input, regardless of how many were sampled. */
    trueCount: number;
}

function byPassengerId(
    a: PassengerPosition,
    b: PassengerPosition,
): number {
    return a.passenger_id.localeCompare(b.passenger_id);
}

/** FNV-1a string hash. Deterministic, no Math.random/Date.now involved. */
function hashPassengerId(id: string): number {
    let hash = 0x811c9dc5;

    for (let index = 0; index < id.length; index += 1) {
        hash ^= id.charCodeAt(index);
        hash = Math.imul(hash, 0x01000193);
    }

    return hash >>> 0;
}

function byHashRank(
    a: PassengerPosition,
    b: PassengerPosition,
): number {
    const hashA = hashPassengerId(a.passenger_id);
    const hashB = hashPassengerId(b.passenger_id);

    if (hashA !== hashB) {
        return hashA - hashB;
    }

    // Tie-break on the id itself so ordering never depends on array position.
    return byPassengerId(a, b);
}

/**
 * Select up to `maxMarkers` passengers to draw out of `passengers`,
 * plus the true (unsampled) count.
 *
 * Given the same passenger list and budget, this always returns the same
 * subset. Within budget, every passenger is included.
 */
export function samplePassengers(
    passengers: readonly PassengerPosition[],
    maxMarkers: number,
): PassengerSampleResult {
    const trueCount = passengers.length;
    const budget = Math.max(0, Math.floor(maxMarkers));

    if (trueCount <= budget) {
        return {
            sampled: [...passengers].sort(byPassengerId),
            trueCount,
        };
    }

    const sampled = [...passengers]
        .sort(byHashRank)
        .slice(0, budget)
        .sort(byPassengerId);

    return {
        sampled,
        trueCount,
    };
}
