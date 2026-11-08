// AI contribution: 50% or more AI-generated
import { describe, expect, it } from "vitest";
import { samplePassengers } from "../../src/lib/samplePassengers";

import type { PassengerPosition } from "../../src/types/stationView";

function makePassenger(id: string): PassengerPosition {
    return {
        passenger_id: id,
        group_id: `g-${id}`,
        connection_id: "conn-1",
        position: { x: 0, y: 0 },
        phase: "waiting",
    };
}

function makePassengers(count: number): PassengerPosition[] {
    return Array.from({ length: count }, (_, index) =>
        makePassenger(`p-${String(index).padStart(4, "0")}`),
    );
}

describe("samplePassengers", () => {
    it("draws a marker for every passenger when the count is below the cap", () => {
        const passengers = makePassengers(10);

        const result = samplePassengers(passengers, 60);

        expect(result.sampled).toHaveLength(10);
        expect(result.trueCount).toBe(10);
        expect(result.sampled.map((item) => item.passenger_id).sort()).toEqual(
            passengers.map((item) => item.passenger_id).sort(),
        );
    });

    it("labels the true count even when the sample is smaller", () => {
        const passengers = makePassengers(500);

        const result = samplePassengers(passengers, 60);

        expect(result.trueCount).toBe(500);
        expect(result.sampled.length).toBeLessThanOrEqual(60);
    });

    it("never draws more markers than the budget", () => {
        const passengers = makePassengers(200);

        const result = samplePassengers(passengers, 25);

        expect(result.sampled.length).toBe(25);
    });

    it("is deterministic across repeated calls with the same input", () => {
        const passengers = makePassengers(300);

        const first = samplePassengers(passengers, 40);
        const second = samplePassengers(passengers, 40);

        expect(second.sampled.map((item) => item.passenger_id)).toEqual(
            first.sampled.map((item) => item.passenger_id),
        );
    });

    it("is unaffected by input array order", () => {
        const passengers = makePassengers(300);
        const shuffled = [...passengers].reverse();

        const original = samplePassengers(passengers, 40);
        const reordered = samplePassengers(shuffled, 40);

        expect(reordered.sampled.map((item) => item.passenger_id).sort()).toEqual(
            original.sampled.map((item) => item.passenger_id).sort(),
        );
    });

    it("stays stable when an unrelated passenger leaves the station", () => {
        const passengers = makePassengers(300);
        const before = samplePassengers(passengers, 40);

        // Remove one passenger that was not part of the sample.
        const removedId = passengers
            .map((item) => item.passenger_id)
            .find((id) => !before.sampled.some((item) => item.passenger_id === id));
        expect(removedId).toBeDefined();

        const after = samplePassengers(
            passengers.filter((item) => item.passenger_id !== removedId),
            40,
        );

        expect(after.sampled.map((item) => item.passenger_id)).toEqual(
            before.sampled.map((item) => item.passenger_id),
        );
        expect(after.trueCount).toBe(before.trueCount - 1);
    });

    it("only shifts a small number of markers when a passenger is added", () => {
        const passengers = makePassengers(300);
        const before = samplePassengers(passengers, 40);

        const grown = [...passengers, makePassenger("p-9999")];
        const after = samplePassengers(grown, 40);

        const beforeIds = new Set(before.sampled.map((item) => item.passenger_id));
        const afterIds = new Set(after.sampled.map((item) => item.passenger_id));

        let changed = 0;
        for (const id of beforeIds) {
            if (!afterIds.has(id)) changed += 1;
        }

        // Adding one passenger can bump at most one existing passenger out of the sample.
        expect(changed).toBeLessThanOrEqual(1);
        expect(after.trueCount).toBe(before.trueCount + 1);
    });

    it("sorts the sampled markers by passenger_id for stable draw order", () => {
        const passengers = makePassengers(50);

        const result = samplePassengers(passengers, 10);

        const ids = result.sampled.map((item) => item.passenger_id);
        const sortedIds = [...ids].sort();

        expect(ids).toEqual(sortedIds);
    });

    it("returns an empty sample and zero count for no passengers", () => {
        const result = samplePassengers([], 60);

        expect(result.sampled).toEqual([]);
        expect(result.trueCount).toBe(0);
    });
});
