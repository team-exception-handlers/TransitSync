# AI contribution: 50% or more AI-generated
"""Set up connection protection from passenger transfer routes (#51).

Mathematical Foundations sections 2 and 8 use walking times to choose a hold.
The controller's shifted-exponential walking model uses the same mean and
minimum as passenger generation. Both read these values from the routes.
"""

from collections.abc import Collection, Mapping, Sequence

from simulator.control.break_even import BreakEvenWeights
from simulator.control.hold_search import HoldSearch, HoldSearchSettings
from simulator.control.strategies.connection_protection import (
    ConnectionProtectionStrategy,
)
from simulator.control.walking_cdf import ShiftedExponentialCdf
from simulator.passengers import TransferRoute

# These defaults cannot change. Each call creates its own searches.
_DEFAULT_WEIGHTS = BreakEvenWeights()
_DEFAULT_SETTINGS = HoldSearchSettings()


def build_connection_protection(
    routes: Sequence[TransferRoute],
    headways_s: Mapping[str, float],
    platform_ids: Collection[str],
    *,
    weights: BreakEvenWeights = _DEFAULT_WEIGHTS,
    settings: HoldSearchSettings = _DEFAULT_SETTINGS,
) -> ConnectionProtectionStrategy:
    """Build a strategy using the same routes as passenger generation.

    ``platform_ids`` lists the network's platforms. ``headways_s`` gives the time
    between services in seconds for each platform that receives transfers.
    ``weights`` sets cost weights; ``settings`` sets which hold lengths to try.
    Return a new strategy with read-only copies of its maps and its own log.
    Raise ``ValueError`` for bad inputs, unknown platforms, missing or extra
    headways, or routes to one platform with different walking means or minimums.
    """
    _validate_topology_inputs(routes, platform_ids)
    if not isinstance(headways_s, Mapping):
        raise ValueError("headways_s must be a mapping")
    # Keep the first route so an error can show both routes and their walk times.
    destinations: dict[str, TransferRoute] = {}
    for route in routes:
        _validate_route(route, platform_ids, destinations)
        destinations.setdefault(route.connecting_platform_id, route)
    missing = destinations.keys() - headways_s.keys()
    extra = headways_s.keys() - destinations.keys()
    if missing or extra:
        raise ValueError(
            f"headways_s: missing platforms {sorted(missing)!r}; "
            f"extra platforms {sorted(extra, key=repr)!r}"
        )
    # Set up every transfer destination, even when nobody is walking there yet.
    searches = {
        platform: HoldSearch(
            ShiftedExponentialCdf(route.walking_mean_s, route.walking_min_s),
            weights,
            settings,
        )
        for platform, route in destinations.items()
    }
    # The strategy checks the headway values and copies both maps.
    return ConnectionProtectionStrategy(searches, headways_s)


def _validate_topology_inputs(
    routes: Sequence[TransferRoute], platform_ids: Collection[str]
) -> None:
    """Check the route list and platform IDs before looking up platforms."""
    if (
        isinstance(routes, str | bytes)
        or not isinstance(routes, Sequence)
        or any(not isinstance(route, TransferRoute) for route in routes)
    ):
        raise ValueError("routes must be a sequence of TransferRoute")
    if (
        isinstance(platform_ids, str | bytes)
        or not isinstance(platform_ids, Collection)
        or any(not isinstance(p, str) or not p.strip() for p in platform_ids)
    ):
        raise ValueError("platform_ids must contain non-empty platform IDs")


def _validate_route(
    route: TransferRoute,
    platform_ids: Collection[str],
    destinations: Mapping[str, TransferRoute],
) -> None:
    """Check platforms and require matching walk times for routes to one platform."""
    for field in ("feeder_platform_id", "connecting_platform_id"):
        platform = getattr(route, field)
        if platform not in platform_ids:
            raise ValueError(
                f"routes.{field} {platform!r} unknown on {_describe(route)}"
            )
    previous = destinations.get(route.connecting_platform_id)
    # Both the mean and minimum must match to use the same walking model.
    if previous is not None and (
        previous.walking_mean_s != route.walking_mean_s
        or previous.walking_min_s != route.walking_min_s
    ):
        raise ValueError(
            f"routes walking profile conflict at {route.connecting_platform_id!r}: "
            f"{_describe(previous)} versus {_describe(route)}"
        )


def _describe(route: TransferRoute) -> str:
    """Describe a route and its walk times in seconds for error messages."""
    return (
        f"{route.station_id}:{route.feeder_platform_id}->"
        f"{route.connecting_platform_id} "
        f"(walking_mean_s={route.walking_mean_s:g}, "
        f"walking_min_s={route.walking_min_s:g})"
    )
