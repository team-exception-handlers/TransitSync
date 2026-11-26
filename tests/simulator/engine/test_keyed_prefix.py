# AI contribution: 50% or more AI-generated
"""A prefix-bound keyed draw gives exactly the numbers of ``keyed_normal``.

``keyed_normal_from`` hashes the shared start of a key once and copies that
state for each later key (#412). Any difference in how the key text is built
(separators, number formatting, quoting) would change every prediction error,
so these tests compare bit-exact floats rather than approximate values.
"""

import math

from hypothesis import given
from hypothesis import strategies as st

from simulator.engine.random_streams import StreamManager

PARTS = st.one_of(
    st.text(max_size=8),
    st.integers(min_value=-(10**9), max_value=10**9),
    st.floats(allow_nan=False, allow_infinity=False, width=64),
)


def same_bits(first, second):
    """Equal as IEEE-754 doubles, including the sign of zero."""
    return first == second and math.copysign(1, first) == math.copysign(1, second)


def test_decision_prefix_matches_full_key():
    """The run's real shape: decision prefix, then value kind and train ID."""
    streams = StreamManager(42)
    decision = ("REM-12", "mcgill-rem-north", 1234.0)
    draw = streams.keyed_normal_from("prediction_errors", *decision)
    for kind in ("load", "arrival", "transfer"):
        for train_id in ("A", "B12", "", "x'y", 'q"z'):
            expected = streams.keyed_normal(
                "prediction_errors", *decision, kind, train_id
            )
            assert same_bits(draw(kind, train_id), expected)


def test_empty_prefix_and_empty_rest_match():
    """Neither side of the split may add or drop a separator."""
    streams = StreamManager(7)
    assert same_bits(
        streams.keyed_normal_from("prediction_errors")("A", 130),
        streams.keyed_normal("prediction_errors", "A", 130),
    )
    assert same_bits(
        streams.keyed_normal_from("prediction_errors", "A", 130)(),
        streams.keyed_normal("prediction_errors", "A", 130),
    )


def test_keyed_child_manager_prefix_matches():
    """Child managers fold their own key digests into the prefix."""
    child = StreamManager(5).keyed("feeder", 600.0).keyed("group", 3)
    draw = child.keyed_normal_from("walking_times", "P1")
    assert same_bits(draw("p-9"), child.keyed_normal("walking_times", "P1", "p-9"))


@given(
    seed=st.integers(min_value=0, max_value=2**32 - 1),
    prefix=st.lists(PARTS, max_size=4),
    rest=st.lists(PARTS, max_size=4),
)
def test_any_split_of_a_key_matches(seed, prefix, rest):
    """Wherever the key is split, the draw is bit-identical to the full key."""
    streams = StreamManager(seed)
    draw = streams.keyed_normal_from("prediction_errors", *prefix)
    expected = streams.keyed_normal("prediction_errors", *prefix, *rest)
    assert same_bits(draw(*rest), expected)


class Label(str):
    """A str subclass must take the general path and still match."""


def test_bound_kind_and_string_subclass_match():
    """``bind`` adds to the prefix; the one-string fast branch stays exact."""
    streams = StreamManager(11)
    decision = ("T", "P", 90.5)
    load = streams.keyed_normal_from("prediction_errors", *decision).bind("load")
    for train_id in ("A", Label("A"), "", "é"):
        expected = streams.keyed_normal(
            "prediction_errors", *decision, "load", train_id
        )
        assert same_bits(load(train_id), expected)
    assert same_bits(
        load(42), streams.keyed_normal("prediction_errors", *decision, "load", 42)
    )
