# AI contribution: Below 50% AI-generated
"""US-2.3, Task 2.3.3 (#47): Ask early-ready trains to wait until scheduled departure.

Uses the Strategy pattern and ignores passenger demand.
The wiki's Mathematical Foundations (Section 6) provides the departure timing and
separation model.
"""

from simulator.control.interface import (
    DecisionController,
    HoldAction,
    ObservationSnapshot,
    as_actions,
)


class ScheduleBasedHoldingStrategy(DecisionController):
    """Ask an early-ready train to wait for its current scheduled departure."""

    name = "schedule_based"

    def evaluate(self, observation: ObservationSnapshot) -> tuple[HoldAction, ...]:
        """Return one hold for remaining seconds, or no action if on time or late."""
        hold_s = observation.scheduled_departure_s - observation.time_s
        # A train that is on time or late leaves without a hold.
        hold = None
        if hold_s > 0:
            hold = HoldAction(observation.train_id, hold_s, self.name)
        return as_actions(hold)
