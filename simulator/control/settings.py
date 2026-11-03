# AI contribution: 50% or more AI-generated
"""Control settings: which strategy a run uses (US-2.3, Task 2.3.1, #45).

Read from the optional ``"control"`` object of a scenario, for example
``{"control": {"strategy": "no_control"}}``. The name is checked against the
strategy registry when the scenario loads, so a typo fails before the run
starts instead of at the first decision point.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from simulator.control.registry import StrategyRegistry
from simulator.control.strategies import STRATEGIES

DEFAULT_STRATEGY = "no_control"
CONTROL_FIELDS = frozenset({"strategy"})
OPERATING_RULES_FIELDS = frozenset({"max_hold_time", "min_safe_gap", "rule_action_map"})


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


@dataclass(frozen=True, slots=True)
class OperatingRulesConfig:
    """Centralized configuration for transit operating rules and safety limits."""

    max_hold_time: float = (
        300.0  # Maximum allowable hold time at a station/signal (seconds)
    )
    min_safe_gap: float = (
        60.0  # Minimum safe headway / temporal gap between units (seconds)
    )
    rule_action_map: Mapping[str, str] = field(
        default_factory=lambda: {
            "max_hold_exceeded": "CLAMP",
            "headway_violation": "REFUSE",
            "one_hop_violation": "REFUSE",
        }
    )

    def to_dict(self) -> dict[str, Any]:
        """Return the operating rules as saved in a scenario file and manifest."""
        return {
            "max_hold_time": self.max_hold_time,
            "min_safe_gap": self.min_safe_gap,
            "rule_action_map": dict(self.rule_action_map),
        }


class OperatingRulesError(ValueError):
    """An ``operating_rules`` value is invalid."""


def parse_operating_rules(value: object) -> OperatingRulesConfig:
    """Validate the ``operating_rules`` object of a scenario."""
    if value is None:
        return OperatingRulesConfig()
    if not isinstance(value, Mapping):
        raise OperatingRulesError("operating_rules: must be an object")
    unknown = sorted(value.keys() - OPERATING_RULES_FIELDS)
    if unknown:
        raise OperatingRulesError(f"operating_rules.{unknown[0]}: unknown field")

    kwargs = {}
    if "max_hold_time" in value:
        val = value["max_hold_time"]
        if isinstance(val, bool) or not isinstance(val, int | float) or val <= 0:
            raise OperatingRulesError(
                "operating_rules.max_hold_time: expected positive number"
            )
        kwargs["max_hold_time"] = float(val)

    if "min_safe_gap" in value:
        val = value["min_safe_gap"]
        if isinstance(val, bool) or not isinstance(val, int | float) or val < 0:
            raise OperatingRulesError(
                "operating_rules.min_safe_gap: expected non-negative number"
            )
        kwargs["min_safe_gap"] = float(val)

    if "rule_action_map" in value:
        ram = value["rule_action_map"]
        if not isinstance(ram, Mapping):
            raise OperatingRulesError(
                "operating_rules.rule_action_map: must be an object"
            )

        defaults = OperatingRulesConfig().rule_action_map
        unknown_rules = sorted(ram.keys() - defaults.keys())
        if unknown_rules:
            raise OperatingRulesError(
                f"operating_rules.rule_action_map.{unknown_rules[0]}: unknown rule"
            )

        for k, v in ram.items():
            if v not in ("CLAMP", "REFUSE"):
                raise OperatingRulesError(
                    f"operating_rules.rule_action_map.{k}: "
                    "action must be CLAMP or REFUSE"
                )

        kwargs["rule_action_map"] = {**defaults, **ram}

    return OperatingRulesConfig(**kwargs)
