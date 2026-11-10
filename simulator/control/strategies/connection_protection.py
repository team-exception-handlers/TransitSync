# AI contribution: 50% or more AI-generated
"""Connection protection for US-2.4 (#51), using the Strategy pattern.
Use Mathematical Foundations sections 1, 2 and 8 to choose a hold at decision time.
The simulator checks whether the requested hold is allowed.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, ClassVar

from simulator.control.connection_headways import validate_connection_headways
from simulator.control.decision_audit import DecisionAuditLog
from simulator.control.hold_search import HoldInputs, HoldSearch
from simulator.control.interface import (
    DecisionController,
    HoldAction,
    ObservationSnapshot,
)


@dataclass(frozen=True, eq=False)
class ConnectionProtectionStrategy(DecisionController):
    """Choose a hold using the settings for the train's platform.

    ``searches`` gives the walking model, cost weights and hold lengths to try.
    ``headways_s`` estimates how long passengers wait if they miss this train.
    Times are in seconds. Each strategy keeps its own settings and decision log.
    Instances compare by identity because each belongs to a separate run.
    Raise ``ValueError`` for invalid settings or different platforms in the maps.
    """

    searches: Mapping[str, HoldSearch]
    headways_s: Mapping[str, float]
    name: ClassVar[str] = "connection_protection"
    audit: DecisionAuditLog = field(
        default_factory=DecisionAuditLog, init=False, repr=False, compare=False
    )

    def __post_init__(self) -> None:
        """Check and copy the settings, then make the copies read-only."""
        if not isinstance(self.searches, Mapping):
            raise ValueError("searches must be a mapping")
        searches = dict(self.searches)
        headways = validate_connection_headways(self.headways_s)
        if searches.keys() != headways.keys():
            raise ValueError("headways_s must cover the same platforms as searches")
        for platform_id, search in searches.items():
            if not isinstance(search, HoldSearch):
                raise ValueError(f"searches[{platform_id!r}] must be a HoldSearch")
        object.__setattr__(self, "searches", MappingProxyType(searches))
        object.__setattr__(self, "headways_s", MappingProxyType(headways))

    def evaluate(self, observation: ObservationSnapshot) -> tuple[HoldAction, ...]:
        """Request the best hold in seconds, or return no action.
        Skip platforms without settings. Log each decision at other platforms.
        Raise ``ValueError`` if the observation has no data for the deciding train.
        """
        platform_id = observation.platform_id
        if platform_id not in self.searches:
            return ()
        inputs = HoldInputs.from_observation(observation, self.headways_s[platform_id])
        result = self.searches[platform_id].run(inputs)
        # Keep the reason even when the train should leave without a hold.
        self.audit.record(result)
        if result.chosen is None:
            return ()
        return (HoldAction(observation.train_id, result.hold_s, result.reason),)

    def decision_records(self) -> tuple[dict[str, Any], ...]:
        """Return copies of the logged decisions, oldest first."""
        return self.audit.decision_records()
