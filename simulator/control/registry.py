# AI contribution: 50% or more AI-generated
"""Strategy registry: select a control strategy by name (US-2.3, #49).

Design pattern: Registry with a Factory method. A scenario names its strategy
as text and the registry builds a fresh instance of the matching class, so the
simulator never imports a strategy class directly. Strategies with settings
are built by table-driven dispatch: ``_builders`` pairs each base class with a
small builder that checks only that strategy's inputs.
"""

import inspect
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass

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
        strategy_class = self._classes.get(name) if isinstance(name, str) else None
        if strategy_class is None:
            raise UnknownStrategyError(
                f"unknown strategy {name!r}; available: {', '.join(self.names())}"
            )
        inputs = _BuildInputs(
            target_headways_s=target_headways_s,
            walking_by_platform=walking_by_platform,
            rolling_horizon=rolling_horizon,
            hold_search=hold_search,
            weights=weights,
            connection_headways_s=connection_headways_s,
            irregularity_threshold=irregularity_threshold,
        )
        # The first matching base class decides which inputs are required.
        for base_class, builder in _builders():
            if issubclass(strategy_class, base_class):
                return builder(strategy_class, inputs)
        # Strategies without settings (no control, schedule-based) take none.
        _reject_unused(
            inputs,
            "irregularity_threshold",
            "connection_headways_s",
            "target_headways_s",
        )
        return strategy_class()


@dataclass(frozen=True)
class _BuildInputs:
    """Every optional setting ``StrategyRegistry.build`` accepts, in one place."""

    target_headways_s: Mapping[str, float] | None
    walking_by_platform: Mapping[str, WalkingCdf] | None
    rolling_horizon: RollingHorizonSettings | None
    hold_search: HoldSearchSettings | None
    weights: BreakEvenWeights | None
    connection_headways_s: Mapping[str, float] | None
    irregularity_threshold: float | None


# The only strategy each optional setting belongs to, used in error messages.
_SETTING_OWNERS = {
    "irregularity_threshold": "adaptive",
    "target_headways_s": "headway_regulation",
    "connection_headways_s": "connection_protection",
}


def _reject_unused(inputs: _BuildInputs, *fields: str) -> None:
    """Raise for the first setting in ``fields`` given to the wrong strategy.

    The order of ``fields`` is the order errors are reported in.
    """
    for field_name in fields:
        if getattr(inputs, field_name) is not None:
            raise ValueError(
                f"{field_name} only valid for {_SETTING_OWNERS[field_name]}"
            )


def _require_connection_inputs(inputs: _BuildInputs, strategy: str) -> None:
    """Raise unless the walking models and connection headways are both given."""
    if inputs.walking_by_platform is None or inputs.connection_headways_s is None:
        raise ValueError(
            f"walking_by_platform and connection_headways_s required for {strategy}"
        )


def _connection_searches(inputs: _BuildInputs) -> dict[str, HoldSearch]:
    """Build the same connection hold searches for both strategy selections."""
    return {
        platform: HoldSearch(
            cdf,
            inputs.weights or BreakEvenWeights(),
            inputs.hold_search or HoldSearchSettings(),
        )
        for platform, cdf in inputs.walking_by_platform.items()
    }


def _build_adaptive(strategy_class, inputs: _BuildInputs) -> DecisionController:
    """Adaptive switches between its own connection and headway strategies."""
    from simulator.control.strategies.connection_protection import (
        ConnectionProtectionStrategy,
    )
    from simulator.control.strategies.headway_regulation import (
        HeadwayRegulationStrategy,
    )

    if inputs.target_headways_s is None or inputs.irregularity_threshold is None:
        raise ValueError(
            "target_headways_s and irregularity_threshold required for adaptive"
        )
    _require_connection_inputs(inputs, "adaptive")
    connection = ConnectionProtectionStrategy(
        _connection_searches(inputs), inputs.connection_headways_s
    )
    return strategy_class(
        connection,
        HeadwayRegulationStrategy(inputs.target_headways_s),
        inputs.irregularity_threshold,
    )


def _build_connection(strategy_class, inputs: _BuildInputs) -> DecisionController:
    """Connection protection needs walking models and connection headways."""
    _reject_unused(inputs, "irregularity_threshold", "target_headways_s")
    _require_connection_inputs(inputs, "connection_protection")
    return strategy_class(_connection_searches(inputs), inputs.connection_headways_s)


def _build_headway(strategy_class, inputs: _BuildInputs) -> DecisionController:
    """Headway regulation needs only its target gap per platform."""
    _reject_unused(inputs, "irregularity_threshold", "connection_headways_s")
    if inputs.target_headways_s is None:
        raise ValueError("target_headways_s required for headway_regulation")
    return strategy_class(inputs.target_headways_s)


def _build_rolling(strategy_class, inputs: _BuildInputs) -> DecisionController:
    """Rolling horizon wraps a planner; missing settings fall back to defaults."""
    from simulator.control.rolling_horizon import RollingHorizonPlanner

    _reject_unused(
        inputs, "irregularity_threshold", "connection_headways_s", "target_headways_s"
    )
    if inputs.walking_by_platform is None:
        raise ValueError("walking_by_platform required for rolling_horizon")
    return strategy_class(
        RollingHorizonPlanner(
            inputs.walking_by_platform,
            inputs.rolling_horizon or RollingHorizonSettings(),
            inputs.hold_search or HoldSearchSettings(),
            inputs.weights or BreakEvenWeights(),
        )
    )


def _builders() -> tuple[tuple[type, Callable[..., DecisionController]], ...]:
    """Pair each strategy base class with the function that builds it.

    Table-driven dispatch: adding a strategy with settings means one builder
    and one row here. Adaptive is listed first so it is matched before any
    strategy it might extend. Imports are delayed to avoid a cycle with the
    built-in registration in ``simulator.control.strategies``.
    """
    from simulator.control.strategies.adaptive import AdaptiveStrategy
    from simulator.control.strategies.connection_protection import (
        ConnectionProtectionStrategy,
    )
    from simulator.control.strategies.headway_regulation import (
        HeadwayRegulationStrategy,
    )
    from simulator.control.strategies.rolling_horizon import RollingHorizonStrategy

    return (
        (AdaptiveStrategy, _build_adaptive),
        (ConnectionProtectionStrategy, _build_connection),
        (HeadwayRegulationStrategy, _build_headway),
        (RollingHorizonStrategy, _build_rolling),
    )
