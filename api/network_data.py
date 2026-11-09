"""Load the immutable reference network and describe its scenario coverage."""

from collections.abc import Mapping
from functools import lru_cache
from pathlib import Path

from simulator.network_config import NetworkConfig, load_network
from simulator.scenario import DatasetMetadata
from simulator.timetable import Platform as TimetablePlatform
from simulator.timetable import ScheduledTrip

CONFIG_ROOT = Path(__file__).resolve().parents[1] / "config"
NETWORK_PATH = CONFIG_ROOT / "reference_network" / "network.json"
DATASET_ID = "reference-network"


@lru_cache(maxsize=1)
def load_reference_network() -> NetworkConfig:
    """Load committed schedules once per API process."""
    return load_network(NETWORK_PATH)


def dataset_metadata(network: NetworkConfig) -> DatasetMetadata:
    """Describe the reference network's service dates and interchange coverage."""
    platforms = {platform.platform_id: platform for platform in network.platforms}
    service_ends = {platform.interchange_id: 0 for platform in network.platforms}
    for trips in network.schedules.values():
        for trip in trips:
            _record_trip_service_end(trip, platforms, service_ends)
    service_dates = tuple(sorted(network.schedules))
    return DatasetMetadata(
        dataset_id=DATASET_ID,
        coverage_start=min(service_dates),
        coverage_end=max(service_dates),
        service_day_end_s_by_interchange=service_ends,
        interchange_ids=frozenset(service_ends),
        service_dates=service_dates,
    )


def _record_trip_service_end(
    trip: ScheduledTrip,
    platforms: Mapping[str, TimetablePlatform],
    service_ends: dict[str, int],
) -> None:
    """Update each interchange horizon using absolute scheduled seconds."""
    for visit in trip.visits:
        interchange_id = platforms[visit.platform_id].interchange_id
        service_ends[interchange_id] = max(
            service_ends[interchange_id], visit.departure_s
        )
