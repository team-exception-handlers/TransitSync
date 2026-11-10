# AI contribution: 50% or more AI-generated
"""Strategy registry: select a control strategy by name (US-2.3, #49).

Design pattern: Registry with a Factory method. A scenario names its strategy
as text and the registry builds a fresh instance of the matching class, so the
simulator never imports a strategy class directly.
"""

import inspect
from collections.abc import Iterable, Mapping

from simulator.control.break_even import BreakEvenWeights
from simulator.control.hold_search import HoldSearch, HoldSearchSettings
from simulator.control.interface import DecisionController
from simulator.control.planning import RollingHorizonSettings
from simulator.control.walking_cdf import WalkingCdf


class UnknownStrategyError(ValueError):
    """A strategy name does not match any registered strategy."""


class StrategyRegistry:
    """Lookup table from strategy name to concrete ``DecisionController`` class.

    Raises ``ValueError`` if a class is abstract, unnamed or reuses a name.
    """

    def __init__(self, strategy_classes: Iterable[type[DecisionController]]) -> None:
        self._classes: dict[str, type[DecisionController]] = {}
        for strategy_class in strategy_classes:
            self._register(strategy_class)

    def _register(self, strategy_class: type[DecisionController]) -> None:
        # Checked when the table is built, so a broken strategy fails at
        # import time instead of in the middle of a run
        if not inspect.isclass(strategy_class) or not issubclass(
            strategy_class, DecisionController
        ):
            raise ValueError(f"{strategy_class!r} is not a DecisionController")
        if inspect.isabstract(strategy_class):
            raise ValueError(f"{strategy_class.__name__} does not implement evaluate")
        name = getattr(strategy_class, "name", None)
        if not isinstance(name, str) or not name.strip():
            raise ValueError(
                f"{strategy_class.__name__}.name must be a non-empty string"
            )
        if name in self._classes:
            raise ValueError(f"strategy name {name!r} is registered twice")
        self._classes[name] = strategy_class

    def names(self) -> tuple[str, ...]:
        """Return every registered strategy name, sorted for stable output."""
        return tuple(sorted(self._classes))

    def __contains__(self, name: object) -> bool:
        return name in self._classes

    def build(
        self,
        name: str,
        *,
        target_headways_s: Mapping[str, float] | None = None,
        walking_by_platform: Mapping[str, WalkingCdf] | None = None,
        rolling_horizon: RollingHorizonSettings | None = None,
        hold_search: HoldSearchSettings | None = None,
        weights: BreakEvenWeights | None = None,
        connection_headways_s: Mapping[str, float] | None = None,
        irregularity_threshold: float | None = None,
    ) -> DecisionController:
        """Build a strategy with its headways or route-specific walking CDFs.

        Raise UnknownStrategyError for unknown names, listing valid choices.
        Raise ValueError for missing inputs or headways on another strategy.
        Headways and search limits are seconds. Both connection protection and
        rolling horizon use the supplied walking models and objective weights.
        """
        # Delay this import to avoid a cycle with built-in registration.
        from simulator.control.strategies.adaptive import AdaptiveStrategy
        from simulator.control.strategies.connection_protection import (
            ConnectionProtectionStrategy,
        )
        from simulator.control.strategies.headway_regulation import (
            HeadwayRegulationStrategy,
        )

        strategy_class = self._classes.get(name) if isinstance(name, str) else None
        if strategy_class is None:
            raise UnknownStrategyError(
                f"unknown strategy {name!r}; available: {', '.join(self.names())}"
            )
        if issubclass(strategy_class, AdaptiveStrategy):
            if target_headways_s is None or irregularity_threshold is None:
                raise ValueError(
                    "target_headways_s and irregularity_threshold required for adaptive"
                )
            if walking_by_platform is None or connection_headways_s is None:
                raise ValueError(
                    "walking_by_platform and connection_headways_s required "
                    "for adaptive"
                )
            connection = ConnectionProtectionStrategy(
                _connection_searches(walking_by_platform, weights, hold_search),
                connection_headways_s,
            )
            return strategy_class(
                connection,
                HeadwayRegulationStrategy(target_headways_s),
                irregularity_threshold,
            )

        if irregularity_threshold is not None:
            raise ValueError("irregularity_threshold only valid for adaptive")
        if issubclass(strategy_class, ConnectionProtectionStrategy):
            if target_headways_s is not None:
                raise ValueError("target_headways_s only valid for headway_regulation")
            if walking_by_platform is None or connection_headways_s is None:
                raise ValueError(
                    "walking_by_platform and connection_headways_s required "
                    "for connection_protection"
                )
            return strategy_class(
                _connection_searches(walking_by_platform, weights, hold_search),
                connection_headways_s,
            )
        if connection_headways_s is not None:
            raise ValueError(
                "connection_headways_s only valid for connection_protection"
            )
        if issubclass(strategy_class, HeadwayRegulationStrategy):
            if target_headways_s is None:
                raise ValueError("target_headways_s required for headway_regulation")
            return strategy_class(target_headways_s)
        if target_headways_s is not None:
            raise ValueError("target_headways_s only valid for headway_regulation")
        from simulator.control.rolling_horizon import RollingHorizonPlanner
        from simulator.control.strategies.rolling_horizon import RollingHorizonStrategy

        if issubclass(strategy_class, RollingHorizonStrategy):
            if walking_by_platform is None:
                raise ValueError("walking_by_platform required for rolling_horizon")
            return strategy_class(
                RollingHorizonPlanner(
                    walking_by_platform,
                    rolling_horizon or RollingHorizonSettings(),
                    hold_search or HoldSearchSettings(),
                    weights or BreakEvenWeights(),
                )
            )
        return strategy_class()


def _connection_searches(
    walking_by_platform: Mapping[str, WalkingCdf],
    weights: BreakEvenWeights | None,
    hold_search: HoldSearchSettings | None,
) -> dict[str, HoldSearch]:
    """Build the same connection hold searches for both strategy selections."""
    return {
        platform: HoldSearch(
            cdf,
            weights or BreakEvenWeights(),
            hold_search or HoldSearchSettings(),
        )
        for platform, cdf in walking_by_platform.items()
    }
