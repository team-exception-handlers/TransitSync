# AI contribution: 50% or more AI-generated
"""Break-even rule for one candidate hold (US-2.2, Task 2.2.2, #42).

Implements Mathematical Foundations section 1:

    Benefit(h) = N(h) * H * w_wait
    Cost(h)    = L * h * w_onboard + downstream cost
    Hold if Benefit(h) > Cost(h)

Both sides are in passenger-seconds. One person delayed 60 s counts the same
as 60 people delayed 1 s, so the two sides can be compared directly.

This is a pure function with no simulator dependency: it takes numbers and
returns numbers, so it can be checked against values worked out by hand.
N(h) comes from ``expected_arrivals`` (#41) and the search over hold lengths
is #43. The downstream cost defaults to 0 until downstream evaluation (#62)
supplies it.
"""

from dataclasses import dataclass

from simulator.control.validation import finite_number

# Waiting on a platform feels worse than riding, so it is weighted more.
# Assumed values until the rider survey gives the ratio (section 1)
DEFAULT_W_WAIT = 2.0
DEFAULT_W_ONBOARD = 1.0


@dataclass(frozen=True, slots=True)
class BreakEvenWeights:
    """Weights w_wait and w_onboard, with no unit.

    Raises ``ValueError`` if a weight is negative or not a finite number.
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

    ``hold_s`` is in seconds, ``n_caught`` in passengers, and the benefit and
    cost in passenger-seconds. Value Object: the search (#43) compares these
    and the decision audit (#44) records them as they are.
    """

    hold_s: float
    n_caught: float
    benefit_ps: float
    cost_ps: float

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
) -> BreakEvenResult:
    """Return the benefit and cost of holding ``hold_s`` seconds.

    Args:
        hold_s: h, hold length in seconds.
        n_caught: N(h), extra passengers the hold lets connect.
        headway_s: H, seconds those passengers would otherwise wait for the
            next train.
        load: L, passengers already on board, who each lose ``hold_s``.
        weights: w_wait and w_onboard.
        downstream_cost_ps: knock-on delay to later trains, in
            passenger-seconds.

    Raises:
        ValueError: any input is negative or not a finite number.
    """
    hold = finite_number("hold_s", hold_s, 0.0)
    caught = finite_number("n_caught", n_caught, 0.0)
    headway = finite_number("headway_s", headway_s, 0.0)
    onboard = finite_number("load", load, 0.0)
    downstream = finite_number("downstream_cost_ps", downstream_cost_ps, 0.0)
    # Time saved: each caught passenger avoids waiting a full headway
    benefit = caught * headway * weights.w_wait
    # Time lost: everyone on board waits the whole hold, plus later trains
    cost = onboard * hold * weights.w_onboard + downstream
    return BreakEvenResult(hold, caught, benefit, cost)
