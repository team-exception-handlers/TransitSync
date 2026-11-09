// AI contribution: 50% or more AI-generated

import type { PassengerMovement, PassengerTrack } from "../types/stationView";

export function derivePassengerMovements(tracks: PassengerTrack[]): PassengerMovement[] {
    return (tracks || []).flatMap((track) => {
        const first = track.samples[0];
        const last = track.samples[track.samples.length - 1];

        if (!first || !last) {
            return [];
        }

        return [{
            passenger_id: track.passenger_id,
            group_id: track.group_id,
            connection_id: track.connection_id!, // Non-null assertion
            start_time_s: first.time_s,
            end_time_s: last.time_s,
            path: track.samples.map((s) => ({
                time_s: s.time_s,
                position: s.position,
            })),
            status: last.phase,
        }];
    });
}