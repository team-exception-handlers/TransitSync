# AI contribution: 50% or more AI-generated
"""Pair a holding run with a no-holding run of one connection (US-4.1).

A Facade over ``SimulationRunService``: both runs share its cache and the
scenario's master seed (common random numbers), so they differ only in holding.
The response also splits the pair's passengers into better off, worse off and
unaffected (US-6.3, #285).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from api.passenger_outcomes import match_passengers
from api.passenger_split import PassengerSplit, split_passengers
from api.simulation_run import SimulationRunRequest, SimulationRunService
from api.station_view import SimulationRunResponse

# Holding side when Scenario setup still selects "no_control".
DEFAULT_HOLDING_STRATEGY = "connection_protection"
NO_HOLDING_STRATEGY = "no_control"
# Dropped from the baseline so moving these sliders reuses its cached run.
CONTROL_ONLY_FIELDS = frozenset(
    {"irregularity_threshold", "error_magnitude", "max_hold_time"}
)


class SimulationComparisonResponse(BaseModel):
    """Both runs plus their shared date (ISO), seed and duration (seconds)."""

    model_config = ConfigDict(extra="forbid")

    holding: SimulationRunResponse
    no_holding: SimulationRunResponse
    holding_strategy: str = Field(min_length=1)
    service_date: str = Field(min_length=10, max_length=10)
    master_seed: int = Field(ge=0)
    duration_s: float = Field(gt=0, allow_inf_nan=False)
    passenger_split: PassengerSplit


def paired_requests(
    request: SimulationRunRequest,
) -> tuple[SimulationRunRequest, SimulationRunRequest]:
    """Return ``(holding, no_holding)`` requests for one set of settings.

    Holding keeps the chosen strategy, or ``DEFAULT_HOLDING_STRATEGY`` for no
    control. Connection, demand and disruption are the same on both sides.
    """
    holding = request
    if request.strategy == NO_HOLDING_STRATEGY:
        # No adaptive threshold to drop: validation rejects one on no control.
        holding = request.model_copy(update={"strategy": DEFAULT_HOLDING_STRATEGY})
    return holding, no_holding_request(request)


def no_holding_request(request: SimulationRunRequest) -> SimulationRunRequest:
    """Return the no-control baseline, shared by both comparison endpoints."""
    baseline_fields = request.model_dump(exclude=CONTROL_ONLY_FIELDS)
    baseline_fields["strategy"] = NO_HOLDING_STRATEGY
    return SimulationRunRequest.model_validate(baseline_fields)


def run_comparison(
    service: SimulationRunService, request: SimulationRunRequest
) -> SimulationComparisonResponse:
    """Run (or reuse from cache) both sides of a comparison.

    Raises ``UnknownConnectionError`` for an unknown connection; simulator and
    file errors propagate to the route, as for a single run.
    """
    holding_request, baseline_request = paired_requests(request)
    # Looked up first so an unknown connection fails before any run starts.
    scenario = service.starting_conditions(request.connection_id)
    holding = service.run(holding_request)
    no_holding = service.run(baseline_request)
    # Sides that are not one pair raise ValueError, which the route logs as a 500
    matched = match_passengers(
        holding.passenger_outcomes, no_holding.passenger_outcomes
    )
    return SimulationComparisonResponse(
        holding=holding,
        no_holding=no_holding,
        passenger_split=split_passengers(matched),
        holding_strategy=holding_request.strategy,
        service_date=scenario.service_date.isoformat(),
        master_seed=scenario.master_seed,
        duration_s=float(scenario.duration_s),
    )
