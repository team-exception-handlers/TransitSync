// AI contribution: 50% or more AI-generated

import type {
    NetworkSnapshot,
    PassengerPosition,
    PassengerTrack,
    Point,
    StationViewData,
    TrainAtPlatform,
    TrainMovementEvent,
} from "../types/stationView";

import { prepareCorridorInterpolation } from "./interpolateAlongCorridor";

type PreparedInterpolation = ReturnType<typeof prepareCorridorInterpolation>;

// Loaded runs are treated as immutable. Weak keys let replaced runs be collected.
const interpolationByRun = new WeakMap<StationViewData, Map<PassengerTrack, (PreparedInterpolation | undefined)[]>>();

function getPreparedInterpolations(data: StationViewData) {
    const cached = interpolationByRun.get(data);
    if (cached) return cached;

    const paths = getCorridorPathByConnection(data);
    const prepared = new Map(data.passenger_tracks.map((track) => [
        track,
        track.samples.map((sample, index) => {
            const next = track.samples[index + 1];
            if (sample.phase !== "walking" || !next || next.time_s <= sample.time_s) {
                return undefined;
            }
            return prepareCorridorInterpolation(
                sample.position, next.position, paths.get(track.connection_id),
            );
        }),
    ]));
    interpolationByRun.set(data, prepared);
    return prepared;
}

function clampTime(
    time_s: number,
    duration_s: number,
): number {
    if (!Number.isFinite(time_s)) {
        return 0;
    }

    return Math.max(
        0,
        Math.min(time_s, duration_s),
    );
}

function getPassengerPosition(
    track: PassengerTrack,
    time_s: number,
    interpolations: readonly (PreparedInterpolation | undefined)[],
): PassengerPosition | null {
    const samples = track.samples;

    if (
        samples.length === 0 ||
        time_s < samples[0].time_s
    ) {
        return null;
    }

    let left = 0;
    let right = samples.length;

    while (left < right) {
        const middle = Math.floor(
            (left + right) / 2,
        );

        if (samples[middle].time_s <= time_s) {
            left = middle + 1;
        } else {
            right = middle;
        }
    }

    const index = left - 1;

    const current = samples[index];
    const next = samples[index + 1];

    if (current.phase === "boarded") {
        return null;
    }

    let position = {
        ...current.position,
    };

    if (
        current.phase === "walking" &&
        next &&
        next.time_s > current.time_s
    ) {
        const fraction =
            (time_s - current.time_s) /
            (next.time_s - current.time_s);

        position = interpolations[index]!(fraction);
    }

    return {
        passenger_id: track.passenger_id,
        group_id: track.group_id,
        connection_id: track.connection_id,
        position,
        phase: current.phase,
    };
}

function compareTrainEvents(
    a: TrainMovementEvent,
    b: TrainMovementEvent,
): number {
    if (a.time_s !== b.time_s) {
        return a.time_s - b.time_s;
    }

    const priorityA =
        a.event_type === "train_arrival" ? 0 : 1;

    const priorityB =
        b.event_type === "train_arrival" ? 0 : 1;

    if (priorityA !== priorityB) {
        return priorityA - priorityB;
    }

    return a.train_id.localeCompare(b.train_id);
}

function getCorridorPathByConnection(
    data: StationViewData,
): Map<string, Point[]> {
    const corridorById = new Map(
        data.corridors.map((corridor) => [
            corridor.id,
            corridor.path,
        ]),
    );

    const result = new Map<string, Point[]>();

    for (const connection of data.connections) {
        const path = corridorById.get(connection.corridor_id);

        if (path) {
            result.set(connection.id, path);
        }
    }

    return result;
}

function getTrainsAtTime(
    data: StationViewData,
    time_s: number,
): TrainAtPlatform[] {

    const events = [
        ...data.train_events,
    ].sort(compareTrainEvents);

    const latestByTrain = new Map<string, TrainMovementEvent>();

    for (const event of events) {
        if (event.time_s > time_s) {
            break;
        }

        latestByTrain.set(
            event.train_id,
            event,
        );
    }

    const trains: TrainAtPlatform[] = [];

    for (const event of latestByTrain.values()) {
        if (event.event_type !== "train_arrival") {
            continue;
        }

        trains.push({
            train_id: event.train_id,
            station_id: event.station_id,
            platform_id: event.platform_id,
            arrived_s: event.time_s,
        });
    }

    return trains.sort((a, b) =>
        a.train_id.localeCompare(b.train_id),
    );
}

// seeking and playback.
export function getNetworkSnapshot(
    data: StationViewData,
    requestedTime_s: number,
): NetworkSnapshot {
    const time_s = clampTime(
        requestedTime_s,
        data.duration_s,
    );

    const interpolations = getPreparedInterpolations(data);

    const passengers = data.passenger_tracks
        .map((track) =>
            getPassengerPosition(
                track,
                time_s,
                interpolations.get(track)!,
            ),
        )
        .filter(
            (passenger): passenger is PassengerPosition =>
                passenger !== null,
        )
        .sort((a, b) =>
            a.passenger_id.localeCompare(b.passenger_id),
        );

    const trains_at_platforms = getTrainsAtTime(
        data,
        time_s,
    );

    return {
        time_s,
        passengers,
        trains_at_platforms,
    };
}
