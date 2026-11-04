# AI contribution: 50% or more AI-generated
"""Strategy registry: select a control strategy by name (US-2.3, #49).

Design pattern: Registry with a Factory method. A scenario names its strategy
as text and the registry builds a fresh instance of the matching class, so the
simulator never imports a strategy class directly.
"""

import inspect
from collections.abc import Iterable, Mapping

from simulator.control.interface import DecisionController


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
        self, name: str, *, target_headways_s: Mapping[str, float] | None = None
    ) -> DecisionController:
        """Build a new strategy with supplied headway targets in seconds.

        Raise UnknownStrategyError for unknown names, listing valid choices.
        Raise ValueError for missing or bad targets, or targets on other strategies.
        """
        # Delay this import to avoid a cycle with built-in registration.
        from simulator.control.strategies.headway_regulation import (
            HeadwayRegulationStrategy,
        )

        strategy_class = self._classes.get(name) if isinstance(name, str) else None
        if strategy_class is None:
            raise UnknownStrategyError(
                f"unknown strategy {name!r}; available: {', '.join(self.names())}"
            )
        if issubclass(strategy_class, HeadwayRegulationStrategy):
            if target_headways_s is None:
                raise ValueError("target_headways_s required for headway_regulation")
            return strategy_class(target_headways_s)
        if target_headways_s is not None:
            raise ValueError("target_headways_s only valid for headway_regulation")
        return strategy_class()
