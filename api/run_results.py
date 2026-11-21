# AI contribution: 50% or more AI-generated
"""Results-view sections projected from a completed, cached simulation."""

from pydantic import BaseModel, Field

from api.passenger_metrics import PassengerMetrics
from api.passenger_outcomes import PassengerOutcome
from api.station_view import RunId, TimeSeriesResponse


class RunResultsResponse(BaseModel):
    """Run-relative seconds and the local start clock anchor all chart data."""

    run_id: RunId
    start_clock_s: float = Field(ge=0, allow_inf_nan=False)
    duration_s: float = Field(gt=0, allow_inf_nan=False)
    passenger_metrics: PassengerMetrics
    time_series: TimeSeriesResponse
    passenger_outcomes: list[PassengerOutcome]
