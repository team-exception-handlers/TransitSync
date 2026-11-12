# AI contribution: 50% or more AI-generated
"""US-2.6 #61 Strategy adapter for the rolling-horizon planner (§8).

The planner is pure. This adapter only collects audit records and translates
its first decision to a request; future decisions never enter the event queue.
"""

import copy
from dataclasses import asdict

from simulator.control.decision_audit import (
    DECISION_SCHEMA_VERSION,
    KIND_ROLLING_HORIZON,
)
from simulator.control.interface import (
    DecisionController,
    HoldAction,
    ObservationSnapshot,
    as_actions,
)
from simulator.control.rolling_horizon import RollingHorizonPlanner


class RollingHorizonStrategy(DecisionController):
    """Re-plan at every DepartureDue using fresh immutable observations."""

    name = "rolling_horizon"
    requires_future_visits = True

    def __init__(self, planner: RollingHorizonPlanner) -> None:
        """Bind route CDFs and limits; audit state is private to this run.

        The planner retains no observation or simulator references, and every
        evaluate call solves the current window afresh.
        """
        self.planner = planner
        self._records = []

    def evaluate(self, observation: ObservationSnapshot) -> tuple[HoldAction, ...]:
        """Return at most one current hold; leave safety checks to the pipeline.

        Keep the best future completion for each current duration in the audit,
        so a declined locally helpful hold has a visible downstream explanation.
        """
        plan = self.planner.plan(observation)
        reason = f"rolling horizon: {plan.hold_s:g} s, net {plan.net_ps:g} passenger-s"
        self._records.append(
            {
                "schema_version": DECISION_SCHEMA_VERSION,
                "kind": KIND_ROLLING_HORIZON,
                "strategy": self.name,
                "time_s": observation.time_s,
                "train_id": observation.train_id,
                "station_id": observation.station_id,
                "platform_id": observation.platform_id,
                "rolling_horizon": self.planner.settings.to_dict(),
                "hold_search": self.planner.hold_search.to_dict(),
                "weights": self.planner.weights.to_dict(),
                "chosen_hold_s": plan.hold_s,
                "net_ps": plan.net_ps,
                "local_net_ps": plan.local_net_ps,
                "downstream_cost_ps": plan.downstream_cost_ps,
                "alternatives": [asdict(a) for a in plan.alternatives],
                "combinations_evaluated": plan.combinations_evaluated,
                "plan": [asdict(d) for d in plan.decisions],
                "reason": reason,
            }
        )
        # A zero-second plan means the train leaves on time with no hold.
        hold = None
        if plan.hold_s > 0:
            hold = HoldAction(observation.train_id, plan.hold_s, reason)
        return as_actions(hold)

    def decision_records(self) -> tuple[dict, ...]:
        """Return detached records for the existing decisions.jsonl writer."""
        return tuple(copy.deepcopy(self._records))
