# AI contribution: 50% or more AI-generated
"""Keyed draws in StreamManager (#192, Definition of Done of spike #191).

A keyed draw depends on the master seed, the stream and the key only, never on
how many draws came before it, so paired runs line up (section 9).
"""

import os
import statistics
import subprocess
import sys
import time
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from simulator.engine.random_streams import StreamManager

REPO_ROOT = Path(__file__).resolve().parents[3]
KEY = ("A", "P1", 130.0, "arrival", "B")


def test_same_seed_and_key_give_the_same_draw():
    first = StreamManager(7).keyed_normal("prediction_errors", *KEY)
    assert StreamManager(7).keyed_normal("prediction_errors", *KEY) == first
    # Changing any one part gives another draw
    assert StreamManager(8).keyed_normal("prediction_errors", *KEY) != first
    assert StreamManager(7).keyed_normal("loads", *KEY) != first
    assert StreamManager(7).keyed_normal("prediction_errors", *KEY[:-1], "C") != first


def test_int_and_float_keys_give_the_same_draw():
    streams = StreamManager(7)
    assert streams.keyed_normal("prediction_errors", "A", 130) == streams.keyed_normal(
        "prediction_errors", "A", 130.0
    )


def test_unknown_stream_is_rejected():
    with pytest.raises(ValueError, match="unknown stream"):
        StreamManager(7).keyed_normal("weather", *KEY)


@given(
    keys=st.lists(st.text(min_size=1, max_size=5), min_size=1, max_size=8, unique=True),
    data=st.data(),
)
def test_draws_ignore_order_and_other_keys(keys, data):
    # DoD 2: the same keys in another order, with extra keys between, match
    streams = StreamManager(7)
    first = {key: streams.keyed_normal("prediction_errors", key) for key in keys}
    shuffled = data.draw(st.permutations([*keys, "extra-1", "extra-2"]))
    second = {key: streams.keyed_normal("prediction_errors", key) for key in shuffled}
    assert {key: second[key] for key in keys} == first


def test_keyed_streams_ignore_draws_from_other_keys():
    # A group's generator starts fresh, whatever other groups drew first
    alone = StreamManager(7).keyed("mcgill", "rem-1", 1).get_stream("group_sizes")
    busy = StreamManager(7)
    busy.keyed("mcgill", "rem-0", 1).get_stream("group_sizes").poisson(50, 100)
    after = busy.keyed("mcgill", "rem-1", 1).get_stream("group_sizes")
    assert after.poisson(50, 5).tolist() == alone.poisson(50, 5).tolist()


def test_no_key_returns_the_run_manager():
    streams = StreamManager(7)
    assert streams.keyed() is streams


def test_same_draws_whatever_the_python_hash_seed():
    # DoD 3: hash() changes per process; the keyed draws must not
    code = (
        "from simulator.engine.random_streams import StreamManager;"
        "s = StreamManager(7);"
        "print([s.keyed_normal('prediction_errors', 'A', t) for t in 'ABCD'],"
        " hash('A'))"
    )
    outputs = []
    for hash_seed in ("1", "2"):
        result = subprocess.run(
            [sys.executable, "-c", code],
            cwd=REPO_ROOT,
            env={**os.environ, "PYTHONHASHSEED": hash_seed},
            capture_output=True,
            text=True,
            check=True,
        )
        outputs.append(result.stdout.rsplit(maxsplit=1))
    (draws_1, hash_1), (draws_2, hash_2) = outputs
    assert hash_1 != hash_2
    assert draws_1 == draws_2


def test_draws_are_standard_normal():
    # DoD 4: mean within 0.03 of 0 and SD within 0.03 of 1 over 10,000 draws
    streams = StreamManager(7)
    draws = [streams.keyed_normal("prediction_errors", k) for k in range(10_000)]
    assert abs(statistics.fmean(draws)) < 0.03
    assert abs(statistics.stdev(draws) - 1) < 0.03


def test_100k_draws_take_under_a_second():
    # DoD 5: keeps a full-day run inside the 30 000 ms performance target
    streams = StreamManager(7)
    start = time.perf_counter()
    for k in range(100_000):
        streams.keyed_normal("prediction_errors", "A", "P1", 130.0, "arrival", k)
    assert time.perf_counter() - start < 1.0
