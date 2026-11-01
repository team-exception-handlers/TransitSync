# AI contribution: 50% or more AI-generated
"""Golden regression tests for the break-even chain (US-2.2, #32).

Runs every hand-verified case in ``golden/break_even_cases.json`` through
the full calculation: walking CDF, expected arrivals, break-even and search.
An error here still gives results that look reasonable, so any change in
output fails the build until the cases are re-verified by hand.
"""

import json
import math
from pathlib import Path

import pytest

from simulator.control.break_even import BreakEvenWeights
from simulator.control.expected_arrivals import TransferEstimate
from simulator.control.hold_search import HoldInputs, HoldSearch, HoldSearchSettings
from simulator.control.walking_cdf import LognormalCdf, ShiftedExponentialCdf

GOLDEN = Path(__file__).parent / "golden" / "break_even_cases.json"
CASES = json.loads(GOLDEN.read_text(encoding="utf-8"))["cases"]
# The golden values are written to 4 decimals (6 for passenger counts)
TOLERANCE = 1e-4


def walking_cdf(spec):
    if spec["family"] == "lognormal":
        return LognormalCdf(mu=math.log(spec["median_s"]), sigma=spec["sigma"])
    return ShiftedExponentialCdf(mean_s=spec["mean_s"], min_s=spec["min_s"])


def run_case(case):
    search = HoldSearch(
        walking_cdf(case["walking"]),
        BreakEvenWeights(**case["weights"]),
        HoldSearchSettings(**case["hold_search"]),
    )
    transfers = tuple(
        TransferEstimate(f"g{i}", group["group_size"], group["conn_window_s"])
        for i, group in enumerate(case["transfers"])
    )
    inputs = HoldInputs(
        0.0, "train", "station", "platform", case["load"], case["headway_s"], transfers
    )
    return search.run(inputs)


@pytest.mark.parametrize("case", CASES, ids=[case["name"] for case in CASES])
def test_golden_case_chooses_the_hand_verified_hold(case):
    assert run_case(case).hold_s == case["chosen_hold_s"]


@pytest.mark.parametrize("case", CASES, ids=[case["name"] for case in CASES])
def test_golden_case_matches_every_hand_verified_candidate(case):
    actual = [
        {
            "hold_s": result.hold_s,
            "n_caught": result.n_caught,
            "benefit_ps": result.benefit_ps,
            "cost_ps": result.cost_ps,
        }
        for result in run_case(case).candidates
    ]
    expected = [
        {key: pytest.approx(value, abs=TOLERANCE) for key, value in row.items()}
        for row in case["candidates"]
    ]
    assert actual == expected


def test_golden_file_covers_holds_and_declines():
    # Guards against the file being trimmed to only one kind of decision
    chosen = [case["chosen_hold_s"] for case in CASES]
    assert 0 in chosen
    assert any(hold > 0 for hold in chosen)
