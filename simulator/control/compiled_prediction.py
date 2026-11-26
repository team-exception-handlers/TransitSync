# AI contribution: 50% or more AI-generated
"""Compiled train estimates with the same arithmetic as prediction_error.

The caller validates the inputs and supplies each train's keyed draws (#192);
this module owns no randomness. Fastmath is off so rounding stays exact.
"""

import math
from functools import lru_cache
from threading import Lock

import numpy as np
from numba import njit

# One compile even when several applications start together
_WARMUP_LOCK = Lock()


@njit(cache=True, fastmath=False)
def train_values(rows, draws, now_s, arrival_kappa, load_kappa):
    """Arrival, load and arrival-z per (load, arrival, has next stop) row."""
    result = np.zeros((len(rows), 3))
    position = 0
    for i in range(len(rows)):
        load_z = draws[position]
        position += 1
        result[i, 1] = max(0, round(rows[i, 0] * (1.0 + load_kappa * 0.10 * load_z)))
        if rows[i, 2]:
            z = draws[position]
            position += 1
            horizon = max(rows[i, 1] - now_s, 0.0) / 60.0
            sigma = 60.0 * math.log(horizon + 1.4)
            error = sigma * z
            result[i, 0] = rows[i, 1] + arrival_kappa * error
            result[i, 2] = z
    return result


@lru_cache(maxsize=1)
def warmup():
    """Compile the kernel for a run's array types before the first request."""
    with _WARMUP_LOCK:
        train_values(np.zeros((1, 3)), np.zeros(1), 0.0, 1.0, 1.0)
