# AI contribution: 50% or more AI-generated
"""Control settings: which strategy a run uses (US-2.3, Task 2.3.1, #45).

Read from the optional ``"control"`` object of a scenario, for example
``{"control": {"strategy": "no_control"}}``. The name is checked against the
strategy registry when the scenario loads, so a typo fails before the run
starts instead of at the first decision point.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from simulator.control.registry import StrategyRegistry
from simulator.control.strategies import STRATEGIES

DEFAULT_STRATEGY = "no_control"
CONTROL_FIELDS = frozenset({"strategy"})


class ControlSettingsError(ValueError):
    """A ``control`` value is invalid; the message starts with the field path."""


@dataclass(frozen=True, slots=True)
class ControlSettings:
    """Validated control settings for one scenario."""

    strategy: str = DEFAULT_STRATEGY

    def to_dict(self) -> dict[str, Any]:
        """Return the settings as saved in a scenario file and in the manifest."""
        return {"strategy": self.strategy}


def parse_control_settings(
    value: object, registry: StrategyRegistry = STRATEGIES
) -> ControlSettings:
    """Validate the ``control`` object of a scenario.

    Args:
        value: the parsed JSON value, or ``None`` when the key is missing.
        registry: strategies that may be selected; the built-in ones by default.

    Raises:
        ControlSettingsError: ``control`` is not an object, has an unknown
            field, or names a strategy that is not registered.
    """
    if value is None:
        return ControlSettings()
    if not isinstance(value, Mapping):
        raise ControlSettingsError("control: must be an object")
    unknown = sorted(value.keys() - CONTROL_FIELDS)
    if unknown:
        raise ControlSettingsError(f"control.{unknown[0]}: unknown field")
    strategy = value.get("strategy", DEFAULT_STRATEGY)
    if strategy not in registry:
        choices = ", ".join(registry.names())
        raise ControlSettingsError(
            f"control.strategy: unknown strategy {strategy!r}; choose {choices}"
        )
    return ControlSettings(strategy=strategy)
