"""Deterministic generation of trains from timetables or headways"""

import math
from collections.abc import Sequence

from simulator.trains.train import Train, ScheduledStop

def generate_from_schedule(departure_times_s: Sequence [float], route: Sequence[ScheduledStop], capacity: int, line_id: str, layover_slack_s: float = 0.0,) -> list[Train]:
    """Generate trains from explicit departure times.
    
    The route contains time offsets relative to each train's first departure, rather than absolute simulation times."""

    if not line_id:
        raise ValueError("Line ID cannot be empty")

    if not route:
        raise ValueError("Route cannot be empty")

    if route[0].departure_s != 0:
        raise ValueError("First departure offset must be zero")

    if any(not math.isfinite(t) or t< 0 for t in departure_times_s):
        raise ValueError("Departure times must be finite and >= 0")

    if any(second <= first for first, second in zip(departure_times_s, departure_times_s[1:])):
        raise ValueError("Departure times must be strictly increasing")

    trains = []

    for index, start_time in enumerate(departure_times_s, start = 1):
        scheduled_stops = tuple(ScheduledStop(station_id = stop.station_id, platform_id = stop.platform_id, arrival_s = start_time + stop.arrival_s, departure_s = start_time + stop.departure_s,) for stop in route)

        train = Train(id=f"{line_id}_{index:04d}", capacity = capacity, schedule = scheduled_stops, layover_slack = layover_slack_s,)

        trains.append(train)

    return trains

def generate_from_headway(start_s:float, end_s: float, headway_s: float, route: Sequence[ScheduledStop], capacity: int, line_id: str, layover_slack_s: float = 0.0,) -> list[Train]:
    """Generate trains at uniform departure intervals."""

    if not all( math.isfinite(value) for value in (start_s, end_s, headway_s)):
        raise ValueError("Times must be finite")

    if start_s < 0 or end_s < start_s:
        raise ValueError("Invalid service window")

    if headway_s <= 0:
        raise ValueError("Headway must be positive")

    departure_times = []

    index = 0

    while True:
        departure = start_s + index * headway_s
        if departure > end_s:
            break

        departure_times.append(departure)
        index += 1

    return generate_from_schedule(departure_times_s = departure_times, route = route, capacity = capacity, line_id = line_id, layover_slack_s = layover_slack_s,)