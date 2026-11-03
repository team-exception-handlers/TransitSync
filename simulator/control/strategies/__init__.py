# AI contribution: 50% or more AI-generated
"""Built-in control strategies and the registry that selects them by name.

Every strategy is listed here once. Explicit registration, rather than a
decorator in each module, keeps the list in one place and avoids depending on
which modules happen to have been imported.
"""

from simulator.control.registry import StrategyRegistry
from simulator.control.strategies.no_control import NoControlStrategy
from simulator.control.strategies.schedule_based_holding import (
    ScheduleBasedHoldingStrategy,
)

STRATEGIES = StrategyRegistry((NoControlStrategy, ScheduleBasedHoldingStrategy))
