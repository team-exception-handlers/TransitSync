# AI contribution: Below 50% AI-generated
"""No-control baseline: trains leave as soon as boarding completes.

Implements US-2.3, Task 2.3.2 (#46). Design pattern: Null Object, so the
simulator always has a strategy to ask and never checks for a missing one.
"""

from simulator.control.interface import (
    DecisionController,
    HoldAction,
    ObservationSnapshot,
)


class NoControlStrategy(DecisionController):
    """Never requests a hold; the baseline every other strategy is compared to."""

    name = "no_control"

    def evaluate(self, observation: ObservationSnapshot) -> tuple[HoldAction, ...]:
        """Return no action, whatever the observation contains."""
        return ()
