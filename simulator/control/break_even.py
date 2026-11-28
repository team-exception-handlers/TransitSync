# AI contribution: 50% or more AI-generated
"""Break-even rule for one candidate hold (US-2.2, #42; US-2.4, #206).

Implements Mathematical Foundations section 1:

    Benefit(h) = N(h) * H * w_wait
    Cost(h)    = L * delay * w_onboard + downstream cost
    Hold if Benefit(h) > Cost(h)

N(h) is the additional passengers who can connect because of the hold, H is
the time they would otherwise wait for the next train, and L is the number
already on board.
Times are seconds; benefit and cost are passenger-seconds. The weights express
how waiting and riding time are valued.

Connection protection compares departure with and without a hold, accounting
for mandatory dispatch and minimum-gap waits. For example, a
train ready at 100 s but required to wait until 140 s departs at 160 s after
a requested 60 s hold. That adds 20 s per onboard passenger; only passengers
who connect after 140 s and by 160 s count in N(h).

Callers supply that delay as ``incremental_delay_s``; omitting it charges the
full requested hold h. Downstream cost defaults to zero. The result keeps the
request, estimated departure and extra delay separate for the decision log.

This pure calculation reads no simulator state. The hold search (#43) supplies
N(h) using ``expected_arrivals`` (#41) and the appropriate departure window.
"""

from dataclasses import dataclass

from simulator.control.validation import finite_number

# Use these waiting/riding weights until the rider survey sets their ratio (§1).
DEFAULT_W_WAIT = 2.0
DEFAULT_W_ONBOARD = 1.0


@dataclass(frozen=True, slots=True)
class BreakEvenWeights:
    """Weights for waiting and riding time, with no unit.

    Raise ValueError if either weight is negative or not finite.
    """

    w_wait: float = DEFAULT_W_WAIT
    w_onboard: float = DEFAULT_W_ONBOARD

    def __post_init__(self) -> None:
        # Stored as floats so a scenario's 2 and 2.0 save identically
        for name in ("w_wait", "w_onboard"):
            value = finite_number(f"BreakEvenWeights.{name}", getattr(self, name), 0.0)
            object.__setattr__(self, name, value)

    def to_dict(self) -> dict[str, float]:
        """Return the weights as saved in a scenario, manifest and decision log."""
        return {"w_wait": self.w_wait, "w_onboard": self.w_onboard}


@dataclass(frozen=True, slots=True)
class BreakEvenResult:
    """Both sides of the break-even rule for one hold length.

    Value Object: keeps the requested hold separate from its extra delay.
    Hold, departure and delay are seconds; ``n_caught`` is passengers, and
    benefit/cost are passenger-seconds. Callers that omit departure timing
    receive None in the two optional fields.
    """

    hold_s: float
    n_caught: float
    benefit_ps: float
    cost_ps: float
    departure_s: float | None = None
    incremental_delay_s: float | None = None

    @property
    def net_ps(self) -> float:
        """J(h) = Benefit(h) - Cost(h), in passenger-seconds; may be negative."""
        return self.benefit_ps - self.cost_ps

    @property
    def worthwhile(self) -> bool:
        """True only if the benefit is strictly greater than the cost."""
        return self.benefit_ps > self.cost_ps


def evaluate_hold(
    hold_s: float,
    n_caught: float,
    headway_s: float,
    load: float,
    weights: BreakEvenWeights,
    downstream_cost_ps: float = 0.0,
    *,
    incremental_delay_s: float | None = None,
    departure_s: float | None = None,
) -> BreakEvenResult:
    """Return the passenger benefit and delay cost of a requested hold.

    ``n_caught`` passengers each save ``headway_s`` seconds of waiting. Each
    onboard passenger loses ``incremental_delay_s`` seconds, or ``hold_s``
    when no extra-delay estimate is supplied. Weights scale waiting and riding
    time; downstream cost adds delay to later trains in passenger-seconds.
    ``departure_s`` is an optional departure estimate saved with the result.
    Raise ValueError for negative inputs or values that are not finite.
    """
    hold = finite_number("hold_s", hold_s, 0.0)
    caught = finite_number("n_caught", n_caught, 0.0)
    headway = finite_number("headway_s", headway_s, 0.0)
    onboard = finite_number("load", load, 0.0)
    downstream = finite_number("downstream_cost_ps", downstream_cost_ps, 0.0)
    delay = (
        hold
        if incremental_delay_s is None
        else finite_number("incremental_delay_s", incremental_delay_s, 0.0)
    )
    if departure_s is not None:
        finite_number("departure_s", departure_s, 0.0)
    benefit = caught * headway * weights.w_wait
    # Charge only the extra wait caused by holding when that delay is supplied.
    cost = onboard * delay * weights.w_onboard + downstream
    return BreakEvenResult(
        hold, caught, benefit, cost, departure_s, incremental_delay_s
    )
