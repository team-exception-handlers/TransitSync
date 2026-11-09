// AI contribution: 50% or more AI-generated

export interface Point {
    x: number;
    y: number;
}

export type LineId = "rem" | "orange" | "green" | "blue";

export interface PlatformMappingEntry {
    platform_id: string;
    interchange_id: string;
    line_id: LineId;
    direction_id: number;
    direction_label: string;
    stop_id: string;
    stop_name: string;
    route_ids: string[];
}

export type InterchangeMapping = Record<
    string,
    PlatformMappingEntry[]
>;

export interface Station {
    id: string;
    name: string;
    line_id: LineId;
    position: Point;
}

export interface Platform extends PlatformMappingEntry {
    station_id: string;
    source_feed_id: string;
    position: Point;
    color: string;
}

export interface PlatformLayout {
    station_id: string;
    position: Point;
}

export interface TransferCorridor {
    id: string;
    label: string;
    from_platform_id: string;
    to_platform_id: string;
    path: Point[];
}

export interface Connection {
    id: string;
    label: string;
    from_platform_id: string;
    to_platform_id: string;
    corridor_id: string;
}

export type PassengerPhase =
    | "walking"
    | "queued"
    | "waiting"
    | "boarding"
    | "boarded"
    | "missed";

export interface PassengerSample {
    time_s: number;
    position: Point;
    phase: PassengerPhase;
}

export interface PassengerTrack {
    passenger_id: string;
    group_id: string;
    connection_id: string;
    samples: PassengerSample[];
}

export interface TrainMovementEvent {
    event_type: "train_arrival" | "train_departure";
    train_id: string;
    station_id: string;
    platform_id: string;
    time_s: number;
    scheduled_s: number;
}

// Raw mock data
export interface MockInterchangeData {
    schema_version: 1;
    interchange: {
        id: string;
        name: string;
    };
    start_clock_s: number;
    duration_s: number;
    map: {
        width: number;
        height: number;
    };
    stations: Station[];
    platform_layouts: Record<string, PlatformLayout>;
    corridors: TransferCorridor[];
    connections: Connection[];
    passenger_tracks: PassengerTrack[];
    train_events: TrainMovementEvent[];
}

export interface PassengerPosition {
    passenger_id: string;
    group_id: string;
    connection_id: string;
    position: Point;
    phase: Exclude<PassengerPhase, "boarded">;
}

export interface TrainAtPlatform {
    train_id: string;
    station_id: string;
    platform_id: string;
    arrived_s: number;
}

export interface NetworkSnapshot {
    time_s: number;
    passengers: PassengerPosition[];
    trains_at_platforms: TrainAtPlatform[];
}

export interface PassengerPathPoint {
    time_s: number;
    position: Point;
}

export interface PassengerMovement {
    passenger_id: string;
    group_id: string;
    connection_id: string;
    start_time_s: number;  
    end_time_s: number;    
    path: { time_s: number; position: Point }[];
    status: PassengerPhase;
}

export interface StationViewData
    extends Omit<MockInterchangeData, "platform_layouts"> {
    platforms: Platform[];
    passengers: PassengerMovement[]; // Derived movement data included
}