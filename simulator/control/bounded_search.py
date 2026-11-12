# AI contribution: 50% or more AI-generated
"""Deterministic bounded grid search for rolling-horizon holds (#61).

Small products are exact. Larger products use coordinate ascent from every
current-hold alternative, retaining all stations and marking results approximate.
This modelling choice bounds work without claiming a global optimum. The zero
plan is always scored; ties prefer less total holding, then shorter early holds.
"""

import math
from itertools import product

# Even an affordable four-point default product makes thousands of forecasts.
# Above this threshold, spend the configured budget on bounded improvement.
EXACT_SEARCH_LIMIT = 4096


def plan_rank(holds, result):
    """Stable objective and tie order shared by both search modes."""
    return result.net_ps, -sum(holds), tuple(-h for h in holds)


def search_grid(choices, budget, evaluate):
    """Return best completions per current hold, count, exactness and grid size.

    The minimum budget explores every duration at every station from zero.
    Raise before scoring if that cannot fit; no station is silently dropped.
    Evaluation state and duplicate suppression live only for this decision.
    """
    total = math.prod(len(grid) for grid in choices)
    minimum = 1 + sum(len(grid) - 1 for grid in choices)
    if budget < minimum:
        raise ValueError(
            f"rolling horizon needs at least {minimum} combinations to explore "
            "every station; increase max_combinations or reduce the hold grid"
        )
    exact = total <= min(budget, EXACT_SEARCH_LIMIT)
    states, visited = {}, set()

    def consider(holds):
        if holds in visited or len(visited) >= budget:
            return
        result = evaluate(holds)
        visited.add(holds)
        prior = states.get(holds[0])
        if prior is None or plan_rank(holds, result) > plan_rank(*prior):
            states[holds[0]] = (holds, result)

    if exact:
        for holds in product(*choices):
            consider(holds)
    else:
        _seed_single_station_moves(choices, consider)
        _refine(choices, states, visited, budget, consider)
    return states, len(visited), exact, total


def _seed_single_station_moves(choices, consider):
    """Score the zero plan, then each non-zero hold at one station at a time.

    These are exactly the ``minimum`` combinations ``search_grid`` checked
    against the budget, so every station is explored before refinement.
    """
    zero = (0.0,) * len(choices)
    consider(zero)
    for index, grid in enumerate(choices):
        # grid[0] is the zero hold, already covered by the zero plan above.
        for hold in grid[1:]:
            consider((*zero[:index], hold, *zero[index + 1 :]))


def _refine(choices, states, visited, budget, consider):
    """Improve each current-hold completion until stable or out of budget.

    A complete candidate is evaluated for each move, preserving downstream
    interactions. This heuristic can miss benefits requiring simultaneous
    moves; callers must propagate the approximate flag into explanations.
    """
    changed = True
    while changed and len(visited) < budget:
        previous = {current: pair[0] for current, pair in states.items()}
        for current in sorted(states):
            _improve(current, choices, states, visited, budget, consider)
        changed = any(
            states[current][0] != holds for current, holds in previous.items()
        )


def _improve(current, choices, states, visited, budget, consider):
    """Try one coordinate at a time, stopping immediately at the work limit."""
    for index in range(1, len(choices)):
        origin = states[current][0]
        for hold in choices[index]:
            if len(visited) >= budget:
                return
            consider((*origin[:index], hold, *origin[index + 1 :]))
