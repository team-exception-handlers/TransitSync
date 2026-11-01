# AI contribution: 50% or more AI-generated
"""Hold length search (US-2.2, Task 2.2.3, #43).

Implements Mathematical Foundations section 8:

    h* = argmax over h in X of J(h),  J(h) = Benefit(h) - Cost(h)

X = {0, step, 2 * step, ..., h_max}. ``h = 0`` is always a candidate and has
J(0) = 0, so the search only holds when some candidate nets a strict gain
(section 1). On a tie the shorter hold wins, since it delays the people on
board less for the same result.

``h_max`` here is how far the strategy looks, not a safety rule. The rule
checking layer (US-2.5) still enforces its own maximum hold on whatever the
strategy proposes.

The result keeps every candidate and the inputs behind it, so the decision
audit (#44) can record why each candidate lost without recomputing anything.
"""

from dataclasses import dataclass, field

from simulator.control.break_even import (
    BreakEvenResult,
    BreakEvenWeights,
    evaluate_hold,
)
from simulator.control.expected_arrivals import (
    TransferEstimate,
    total_expected_caught,
    transfers_to_platform,
)
from simulator.control.interface import ObservationSnapshot
from simulator.control.validation import finite_number
from simulator.control.walking_cdf import WalkingCdf

# Assumed until the operating rules (#56) set the maximum hold
DEFAULT_STEP_S = 5.0
DEFAULT_MAX_HOLD_S = 60.0
# Every decision evaluates every candidate, so this bounds the work per
# decision point; 1,000 already allows 1 s steps up to more than 16 minutes
MAX_CANDIDATES = 1000
# Tolerance for "h_max is a whole number of steps", for decimal steps such as
# 0.1 s that floats cannot store exactly
_MULTIPLE_TOLERANCE = 1e-9


@dataclass(frozen=True, slots=True)
class HoldSearchSettings:
    """Increment and upper bound of the candidate hold lengths, in seconds.

    Raises ``ValueError`` if ``step_s`` is not > 0, ``max_hold_s`` is
    negative or not a whole number of steps, or there would be more than
    ``MAX_CANDIDATES`` candidates.
    """

    step_s: float = DEFAULT_STEP_S
    max_hold_s: float = DEFAULT_MAX_HOLD_S

    def __post_init__(self) -> None:
        step = finite_number("HoldSearchSettings.step_s", self.step_s)
        if step <= 0:
            raise ValueError("HoldSearchSettings.step_s must be > 0")
        max_hold = finite_number("HoldSearchSettings.max_hold_s", self.max_hold_s, 0)
        steps = max_hold / step
        if abs(steps - round(steps)) > _MULTIPLE_TOLERANCE:
            raise ValueError(
                "HoldSearchSettings.max_hold_s must be a whole number of step_s"
            )
        if round(steps) + 1 > MAX_CANDIDATES:
            raise ValueError(
                f"HoldSearchSettings gives more than {MAX_CANDIDATES} candidates"
            )
        object.__setattr__(self, "step_s", step)
        object.__setattr__(self, "max_hold_s", max_hold)

    def candidates(self) -> tuple[float, ...]:
        """Return 0, step, ..., max_hold_s in ascending order.

        Each value is ``i * step_s`` rather than a running sum, so rounding
        error does not build up, and the last one is exactly ``max_hold_s``.
        """
        count = round(self.max_hold_s / self.step_s)
        return (*(i * self.step_s for i in range(count)), self.max_hold_s)

    def to_dict(self) -> dict[str, float]:
        """Return the settings as saved in a scenario, manifest and decision log."""
        return {"step_s": self.step_s, "max_hold_s": self.max_hold_s}


@dataclass(frozen=True, slots=True)
class HoldInputs:
    """The observation values one decision is based on.

    ``load`` is L in passengers, ``headway_s`` is H in seconds and
    ``transfers`` are the groups walking to this platform. Raises
    ``ValueError`` for a negative L or H, or if ``transfers`` is not a tuple.
    """

    time_s: float
    train_id: str
    station_id: str
    platform_id: str
    load: float
    headway_s: float
    transfers: tuple[TransferEstimate, ...]

    def __post_init__(self) -> None:
        finite_number("HoldInputs.load", self.load, 0.0)
        finite_number("HoldInputs.headway_s", self.headway_s, 0.0)
        # A tuple keeps the inputs, and the audit record built from them, fixed
        if not isinstance(self.transfers, tuple):
            raise ValueError("HoldInputs.transfers must be a tuple")

    @classmethod
    def from_observation(
        cls, observation: ObservationSnapshot, headway_s: float
    ) -> "HoldInputs":
        """Read L and the transfer groups for the deciding train.

        ``headway_s`` is passed in because how H is found (timetable or the
        next train in the snapshot) is the calling strategy's choice.

        Raises:
            ValueError: the snapshot has no state for the deciding train.
        """
        train = next(
            (t for t in observation.trains if t.train_id == observation.train_id),
            None,
        )
        if train is None:
            raise ValueError(f"observation has no state for {observation.train_id}")
        return cls(
            time_s=observation.time_s,
            train_id=observation.train_id,
            station_id=observation.station_id,
            platform_id=observation.platform_id,
            load=train.onboard_load,
            headway_s=headway_s,
            transfers=transfers_to_platform(observation),
        )


@dataclass(frozen=True, slots=True)
class HoldSearch:
    """Evaluates every candidate hold with one F, set of weights and settings."""

    walking: WalkingCdf
    weights: BreakEvenWeights = field(default_factory=BreakEvenWeights)
    settings: HoldSearchSettings = field(default_factory=HoldSearchSettings)

    def run(self, inputs: HoldInputs) -> "HoldSearchResult":
        """Return every candidate's result and the chosen hold, if any.

        Pure: the same inputs always give the same result, and nothing is
        stored between calls.
        """
        candidates = tuple(
            self._evaluate(inputs, hold_s) for hold_s in self.settings.candidates()
        )
        # max keeps the first of equal values and candidates ascend, so a
        # tie goes to the shorter hold
        best = max(candidates, key=lambda result: result.net_ps)
        chosen = best if best.worthwhile else None
        return HoldSearchResult(self, inputs, candidates, chosen)

    def _evaluate(self, inputs: HoldInputs, hold_s: float) -> BreakEvenResult:
        n_caught = total_expected_caught(inputs.transfers, hold_s, self.walking)
        return evaluate_hold(
            hold_s, n_caught, inputs.headway_s, inputs.load, self.weights
        )


@dataclass(frozen=True, slots=True)
class HoldSearchResult:
    """Outcome of one search: every candidate, and the hold chosen or ``None``."""

    search: HoldSearch
    inputs: HoldInputs
    candidates: tuple[BreakEvenResult, ...]
    chosen: BreakEvenResult | None

    @property
    def hold_s(self) -> float:
        """The hold to request in seconds; 0 when no hold is worthwhile."""
        return 0.0 if self.chosen is None else self.chosen.hold_s

    @property
    def reason(self) -> str:
        """One line explaining the decision, for ``HoldAction`` and the audit."""
        if self.chosen is not None:
            return _describe("hold", self.chosen, ">")
        if not self.inputs.transfers:
            return "no hold: no transfer group is walking to this platform"
        holds = self.candidates[1:]
        if not holds:
            return "no hold: the maximum hold is 0 s"
        # Report the closest call, so the log shows how far from holding it was
        closest = max(holds, key=lambda result: result.net_ps)
        return _describe("no hold: best was", closest, "<=")


def _describe(prefix: str, result: BreakEvenResult, comparison: str) -> str:
    """Format one candidate as '<prefix> 30 s: N caught, benefit > cost'."""
    return (
        f"{prefix} {result.hold_s:g} s: {result.n_caught:.1f} caught, "
        f"benefit {result.benefit_ps:.1f} {comparison} "
        f"cost {result.cost_ps:.1f} passenger-s"
    )
