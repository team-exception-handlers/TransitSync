// AI contribution: 50% or more AI-generated

import type {
    PassengerPhase,
    Point,
    StationViewData,
} from "../types/stationView";

import { derivePassengerMovements } from "./passengerMovements";

const VALID_PHASES = new Set<PassengerPhase>([
    "walking",
    "queued",
    "waiting",
    "boarding",
    "boarded",
    "missed",
]);

function isPoint(value: unknown): value is Point {
    if (typeof value !== "object" || value === null) {
        return false;
    }

    const point = value as Record<string, unknown>;

    return (
        typeof point.x === "number" &&
        Number.isFinite(point.x) &&
        typeof point.y === "number" &&
        Number.isFinite(point.y)
    );
}

function isNonNegativeNumber(value: unknown): value is number {
    return (
        typeof value === "number" &&
        Number.isFinite(value) &&
        value >= 0
    );
}

export function parseStationViewData(
    value: unknown,
): StationViewData {
    if (typeof value !== "object" || value === null) {
        throw new Error("Station view data must be an object");
    }

    const data = value as StationViewData;

    if (data.schema_version !== 1) {
        throw new Error("Unsupported station view schema version");
    }

    if (
        !data.interchange ||
        typeof data.interchange.id !== "string" ||
        typeof data.interchange.name !== "string"
    ) {
        throw new Error("Invalid interchange");
    }

    if (
        !isNonNegativeNumber(data.start_clock_s) ||
        !isNonNegativeNumber(data.duration_s)
    ) {
        throw new Error("Invalid simulation time metadata");
    }

    if (
        !data.map ||
        !isNonNegativeNumber(data.map.width) ||
        !isNonNegativeNumber(data.map.height) ||
        data.map.width === 0 ||
        data.map.height === 0
    ) {
        throw new Error("Invalid map dimensions");
    }

    if (
        !Array.isArray(data.stations) ||
        !Array.isArray(data.platforms) ||
        !Array.isArray(data.corridors) ||
        !Array.isArray(data.connections) ||
        !Array.isArray(data.passenger_tracks) ||
        !Array.isArray(data.train_events)
    ) {
        throw new Error("Invalid station view collections");
    }

    const stationIds = new Set<string>();

    for (const station of data.stations) {
        if (
            typeof station.id !== "string" ||
            typeof station.name !== "string" ||
            !isPoint(station.position)
        ) {
            throw new Error("Invalid station");
        }

        if (stationIds.has(station.id)) {
            throw new Error(`Duplicate station: ${station.id}`);
        }

        stationIds.add(station.id);
    }

    const platformIds = new Set<string>();
    const platformsById = new Map(
        data.platforms.map((platform) => [
            platform.platform_id,
            platform,
        ]),
    );

    for (const platform of data.platforms) {
        if (
            typeof platform.platform_id !== "string" ||
            typeof platform.stop_id !== "string" ||
            typeof platform.direction_label !== "string" ||
            !Number.isInteger(platform.direction_id) ||
            !Array.isArray(platform.route_ids) ||
            !platform.route_ids.every(
                (route) => typeof route === "string",
            ) ||
            !isPoint(platform.position) ||
            !stationIds.has(platform.station_id)
        ) {
            throw new Error("Invalid platform");
        }

        if (platformIds.has(platform.platform_id)) {
            throw new Error(
                `Duplicate platform: ${platform.platform_id}`,
            );
        }

        platformIds.add(platform.platform_id);
    }

    const corridorIds = new Set<string>();

    for (const corridor of data.corridors) {
        if (
            typeof corridor.id !== "string" ||
            !platformIds.has(corridor.from_platform_id) ||
            !platformIds.has(corridor.to_platform_id) ||
            !Array.isArray(corridor.path) ||
            corridor.path.length < 2 ||
            !corridor.path.every(isPoint)
        ) {
            throw new Error(`Invalid corridor: ${corridor.id}`);
        }

        if (corridorIds.has(corridor.id)) {
            throw new Error(`Duplicate corridor: ${corridor.id}`);
        }

        corridorIds.add(corridor.id);
    }

    const connectionIds = new Set<string>();

    for (const connection of data.connections) {
        if (
            typeof connection.id !== "string" ||
            !platformIds.has(connection.from_platform_id) ||
            !platformIds.has(connection.to_platform_id) ||
            !corridorIds.has(connection.corridor_id)
        ) {
            throw new Error(`Invalid connection: ${connection.id}`);
        }

        if (connectionIds.has(connection.id)) {
            throw new Error(`Duplicate connection: ${connection.id}`);
        }

        connectionIds.add(connection.id);
    }

    const passengerIds = new Set<string>();

    for (const track of data.passenger_tracks) {
        if (
            typeof track.passenger_id !== "string" ||
            typeof track.group_id !== "string" ||
            !connectionIds.has(track.connection_id) ||
            !Array.isArray(track.samples)
        ) {
            throw new Error("Invalid passenger track");
        }

        if (passengerIds.has(track.passenger_id)) {
            throw new Error(
                `Duplicate passenger: ${track.passenger_id}`,
            );
        }

        passengerIds.add(track.passenger_id);

        let previousTime = -Infinity;

        for (const sample of track.samples) {
            if (
                !isNonNegativeNumber(sample.time_s) ||
                sample.time_s <= previousTime ||
                sample.time_s > data.duration_s ||
                !isPoint(sample.position) ||
                !VALID_PHASES.has(sample.phase)
            ) {
                throw new Error("Invalid passenger samples");
            }

            previousTime = sample.time_s;
        }
    }

    for (const event of data.train_events) {
        const platform = platformsById.get(event.platform_id);

        if (
            !["train_arrival", "train_departure"].includes(
                event.event_type,
            ) ||
            typeof event.train_id !== "string" ||
            !platform ||
            !isNonNegativeNumber(event.time_s) ||
            !isNonNegativeNumber(event.scheduled_s) ||
            event.time_s > data.duration_s
        ) {
            throw new Error("Invalid train event");
        }

        // Explicit convention for this mock:
        // train-event station_id equals backend stop_id.
        if (event.station_id !== platform.stop_id) {
            throw new Error(
                `Station/stop mismatch for ${event.train_id}`,
            );
        }
    }

    // Return the validated data with passengers automatically derived
    return {
        ...data,
        passengers: derivePassengerMovements(data.passenger_tracks),
    };
}