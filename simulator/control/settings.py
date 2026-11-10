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

The optional ``"prediction_error"`` object holds the error multipliers kappa
(#39). They are always saved, so every run records how accurate its
strategy's information was; all zero is perfect information.

Headway regulation (#48) needs a fixed target in seconds for each platform.
Targets are copied and frozen. The component factory checks known platform
IDs, complete trips and the gap used by the train engine.

Connection protection (#51) has its own service headways in seconds.
They estimate the wait avoided when a passenger catches the current train.
These values stay fixed for the run and are separate from target-gap settings.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field, fields
from sys import maxsize
from types import MappingProxyType
from typing import Any

from simulator.control.break_even import BreakEvenWeights
from simulator.control.connection_headways import validate_connection_headways
from simulator.control.hold_search import HoldSearchSettings
from simulator.control.planning import RollingHorizonSettings
from simulator.control.prediction_error import PredictionErrorSettings
from simulator.control.registry import StrategyRegistry
from simulator.control.strategies import STRATEGIES
from simulator.control.strategies.adaptive import (
    AdaptiveStrategy,
    validate_irregularity_threshold,
)
from simulator.control.strategies.connection_protection import (
    ConnectionProtectionStrategy,
)
from simulator.control.strategies.headway_regulation import HeadwayRegulationStrategy

DEFAULT_STRATEGY = "no_control"
DEFAULT_IRREGULARITY_WINDOW_SIZE = 5
CONTROL_FIELDS = frozenset(
    {
        "strategy",
        "hold_search",
        "weights",
        "target_headways_s",
        "prediction_error",
        "rolling_horizon",
        "irregularity_window_size",
        "irregularity_threshold",
        "connection_headways_s",
    }
)
OPERATING_RULES_FIELDS = frozenset({"max_hold_time", "min_safe_gap", "rule_action_map"})
TARGET_HEADWAY_STRATEGIES = frozenset(
    {HeadwayRegulationStrategy.name, AdaptiveStrategy.name}
)
CONNECTION_HEADWAY_STRATEGIES = frozenset(
    {ConnectionProtectionStrategy.name, AdaptiveStrategy.name}
)


class ControlSettingsError(ValueError):
    """A ``control`` value is invalid; the message starts with the field path."""


@dataclass(frozen=True, slots=True)
class ControlSettings:
    """Validated control settings for one scenario."""

    strategy: str = DEFAULT_STRATEGY
    hold_search: HoldSearchSettings = field(default_factory=HoldSearchSettings)
    weights: BreakEvenWeights = field(default_factory=BreakEvenWeights)
    target_headways_s: Mapping[str, float] | None = None
    prediction_error: PredictionErrorSettings = field(
        default_factory=PredictionErrorSettings
    )
    irregularity_window_size: int = DEFAULT_IRREGULARITY_WINDOW_SIZE
    rolling_horizon: RollingHorizonSettings = field(
        default_factory=RollingHorizonSettings
    )
    connection_headways_s: Mapping[str, float] | None = None
    irregularity_threshold: float | None = None

    def __post_init__(self) -> None:
        """Validate the window length and freeze headways in seconds."""
        size = self.irregularity_window_size
        if type(size) is not int or not 0 < size <= maxsize:
            raise ControlSettingsError(
                "control.irregularity_window_size: expected a positive integer "
                f"up to {maxsize}"
            )
        self._check_irregularity_threshold()
        self._check_connection_headways()
        if self.strategy not in TARGET_HEADWAY_STRATEGIES:
            if self.target_headways_s is not None:
                raise ControlSettingsError(
                    "control.target_headways_s: "
                    "only valid for headway_regulation or adaptive"
                )
            return
        if self.target_headways_s is None:
            raise ControlSettingsError("control.target_headways_s: required")
        try:
            targets = HeadwayRegulationStrategy(self.target_headways_s)
        except ValueError as error:
            raise ControlSettingsError(f"control.target_headways_s: {error}") from error
        object.__setattr__(self, "target_headways_s", targets.target_headways_s)

    def _check_connection_headways(self) -> None:
        """Require connection headways for strategies that protect connections.

        Copy the map so caller changes cannot change an already loaded scenario.
        """
        if self.strategy not in CONNECTION_HEADWAY_STRATEGIES:
            if self.connection_headways_s is not None:
                raise ControlSettingsError(
                    "control.connection_headways_s: "
                    "only valid for connection_protection or adaptive"
                )
            return
        if self.connection_headways_s is None:
            raise ControlSettingsError("control.connection_headways_s: required")
        try:
            headways = validate_connection_headways(self.connection_headways_s)
        except ValueError as error:
            raise ControlSettingsError(
                f"control.connection_headways_s: {error}"
            ) from error
        object.__setattr__(self, "connection_headways_s", MappingProxyType(headways))

    def to_dict(self) -> dict[str, Any]:
        """Return the settings as saved in a scenario file and in the manifest."""
        saved: dict[str, Any] = {
            "strategy": self.strategy,
            "hold_search": self.hold_search.to_dict(),
            "weights": self.weights.to_dict(),
            "prediction_error": self.prediction_error.to_dict(),
        }
        if self.target_headways_s is not None:
            saved["target_headways_s"] = dict(self.target_headways_s)
        if self.strategy == "rolling_horizon":
            saved["rolling_horizon"] = self.rolling_horizon.to_dict()
        if self.irregularity_window_size != DEFAULT_IRREGULARITY_WINDOW_SIZE:
            saved["irregularity_window_size"] = self.irregularity_window_size
        if self.connection_headways_s is not None:
            saved["connection_headways_s"] = dict(self.connection_headways_s)
        if self.irregularity_threshold is not None:
            saved["irregularity_threshold"] = self.irregularity_threshold
        return saved

    def _check_irregularity_threshold(self) -> None:
        """Require a threshold for adaptive mode and validate its range."""
        if self.strategy != AdaptiveStrategy.name:
            if self.irregularity_threshold is not None:
                raise ControlSettingsError(
                    "control.irregularity_threshold: only valid for adaptive"
                )
            return

        if self.irregularity_threshold is None:
            raise ControlSettingsError("control.irregularity_threshold: required")

        try:
            threshold = validate_irregularity_threshold(self.irregularity_threshold)
        except ValueError as error:
            raise ControlSettingsError(str(error)) from error
        object.__setattr__(self, "irregularity_threshold", threshold)


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
    # Check presence too, since an explicitly supplied null still belongs to the field.
    if (
        "connection_headways_s" in value
        and strategy not in CONNECTION_HEADWAY_STRATEGIES
    ):
        raise ControlSettingsError(
            "control.connection_headways_s: "
            "only valid for connection_protection or adaptive"
        )
    if "target_headways_s" in value and strategy not in TARGET_HEADWAY_STRATEGIES:
        raise ControlSettingsError(
            "control.target_headways_s: only valid for headway_regulation or adaptive"
        )
    if "irregularity_threshold" in value and strategy != AdaptiveStrategy.name:
        raise ControlSettingsError(
            "control.irregularity_threshold: only valid for adaptive"
        )
    return ControlSettings(
        strategy=strategy,
        hold_search=_parse_section(value, "hold_search", HoldSearchSettings),
        weights=_parse_section(value, "weights", BreakEvenWeights),
        rolling_horizon=_parse_section(
            value, "rolling_horizon", RollingHorizonSettings
        ),
        target_headways_s=value.get("target_headways_s"),
        prediction_error=_parse_section(
            value, "prediction_error", PredictionErrorSettings
        ),
        irregularity_window_size=value.get(
            "irregularity_window_size", DEFAULT_IRREGULARITY_WINDOW_SIZE
        ),
        connection_headways_s=value.get("connection_headways_s"),
        irregularity_threshold=value.get("irregularity_threshold"),
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
