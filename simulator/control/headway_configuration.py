# AI contribution: 50% or more AI-generated
"""Check saved headway settings before trains start (US-2.3, #48).

The component factory supplies known platform IDs, full trips and the engine
gap. Check trips after the run cutoff too.
Mathematical Foundations (Section 6) leaves separation to the train engine.
This check does not enforce operating limits.
"""

from collections.abc import Collection, Sequence
from sys import float_info

from simulator.control.settings import ControlSettings, ControlSettingsError
from simulator.trains.train import Train


def validate_headway_configuration(
    control: ControlSettings,
    trains: Sequence[Train],
    known_platform_ids: Collection[str],
    minimum_gap_s: float,
) -> None:
    """Check target coverage and the engine gap before components start.

    Use known topology IDs or an explicit set of test platform IDs.
    Pass the same positive finite gap, in seconds, to TrainComponent.
    Include trips after cutoff; other strategies need no target checks.

    Raise ControlSettingsError for unknown platforms, missing targets, a bad
    engine gap or a target below that gap. Equality is allowed.
    """
    targets = control.target_headways_s
    if targets is None:
        return
    if isinstance(known_platform_ids, str) or not isinstance(
        known_platform_ids, Collection
    ):
        raise ControlSettingsError("known_platform_ids: expected a platform collection")
    if (
        isinstance(minimum_gap_s, bool)
        or not isinstance(minimum_gap_s, int | float)
        or not 0 < minimum_gap_s <= float_info.max
    ):
        raise ControlSettingsError("minimum_gap_s: expected finite positive seconds")
    scheduled: set[str] = set()
    required: set[str] = set()
    for train in trains:
        all_platforms, departures = _trip_platforms(train)
        scheduled.update(all_platforms)
        required.update(departures)
    unknown = (scheduled | targets.keys()) - set(known_platform_ids)
    if unknown:
        raise ControlSettingsError(
            f"control.target_headways_s: Unknown platform {sorted(unknown)!r}"
        )
    missing = required - targets.keys()
    if missing:
        raise ControlSettingsError(
            f"control.target_headways_s: Missing target for {sorted(missing)!r}"
        )
    for platform_id, target_s in targets.items():
        if target_s < minimum_gap_s:
            raise ControlSettingsError(
                f"control.target_headways_s: {platform_id!r} below minimum_gap_s "
                f"{minimum_gap_s:g} seconds"
            )


def _trip_platforms(train: Train) -> tuple[set[str], set[str]]:
    """Find all platforms and those that need departure targets."""
    trips = (train.schedule, *train.return_trips)
    scheduled = {stop.platform_id for trip in trips for stop in trip}
    required: set[str] = set()
    for index, trip in enumerate(trips):
        # Skip a trip's final departure only when a return trip follows.
        departures = trip[:-1] if index < len(trips) - 1 else trip
        required.update(stop.platform_id for stop in departures)
    return scheduled, required
