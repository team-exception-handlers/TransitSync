# AI contribution: 50% or more AI-generated
"""Control settings: which strategy a run uses (US-2.3, Task 2.3.1, #45).

Read from the optional ``"control"`` object of a scenario, for example
``{"control": {"strategy": "no_control"}}``. The name is checked against the
strategy registry when the scenario loads, so a typo fails before the run
starts instead of at the first decision point.

The optional ``"hold_search"`` and ``"weights"`` objects configure the
break-even search (US-2.2, #43): the candidate increment and upper bound, and
the weights of waiting against riding time. Both are saved in the manifest,
so every run records the values its holds were chosen with.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field, fields
from typing import Any

from simulator.control.break_even import BreakEvenWeights
from simulator.control.hold_search import HoldSearchSettings
from simulator.control.registry import StrategyRegistry
from simulator.control.strategies import STRATEGIES

DEFAULT_STRATEGY = "no_control"
CONTROL_FIELDS = frozenset({"strategy", "hold_search", "weights"})


class ControlSettingsError(ValueError):
    """A ``control`` value is invalid; the message starts with the field path."""


@dataclass(frozen=True, slots=True)
class ControlSettings:
    """Validated control settings for one scenario."""

    strategy: str = DEFAULT_STRATEGY
    hold_search: HoldSearchSettings = field(default_factory=HoldSearchSettings)
    weights: BreakEvenWeights = field(default_factory=BreakEvenWeights)

    def to_dict(self) -> dict[str, Any]:
        """Return the settings as saved in a scenario file and in the manifest."""
        return {
            "strategy": self.strategy,
            "hold_search": self.hold_search.to_dict(),
            "weights": self.weights.to_dict(),
        }


def parse_control_settings(
    value: object, registry: StrategyRegistry = STRATEGIES
) -> ControlSettings:
    """Validate the ``control`` object of a scenario.

    Args:
        value: the parsed JSON value, or ``None`` when the key is missing.
        registry: strategies that may be selected; the built-in ones by default.

    Raises:
        ControlSettingsError: ``control`` or one of its objects is not an
            object, has an unknown field or an invalid value, or names a
            strategy that is not registered.
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
    return ControlSettings(
        strategy=strategy,
        hold_search=_parse_section(value, "hold_search", HoldSearchSettings),
        weights=_parse_section(value, "weights", BreakEvenWeights),
    )


def _parse_section[T](control: Mapping[str, object], name: str, build: type[T]) -> T:
    """Build one optional nested object, using its defaults when missing.

    The allowed keys are the dataclass fields of ``build``, so a new setting
    only has to be added to its class.
    """
    section = control.get(name)
    if section is None:
        return build()
    if not isinstance(section, Mapping):
        raise ControlSettingsError(f"control.{name}: must be an object")
    allowed = {item.name for item in fields(build)}
    unknown = sorted(section.keys() - allowed)
    if unknown:
        raise ControlSettingsError(f"control.{name}.{unknown[0]}: unknown field")
    try:
        return build(**section)
    except ValueError as error:
        # The class names the bad field; prefix the scenario path to it
        raise ControlSettingsError(f"control.{name}: {error}") from error
