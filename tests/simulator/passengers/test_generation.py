# AI contribution: 50% or more AI-generated
""""""

import math
from collections import Counter

import numpy as np
import pytest
from hypothesis import given
from hypothesis import strategies as st

from simulator.engine.random_streams import STREAM_NAMES, StreamManager
from simulator.passengers import (
    DemandPeriod,
    DemandProfile,
    PassengerGenerator,
    PassengerState,
)


def generate(generator, **overrides):
    arguments = {
        "origin": "mcgill",
        "demand_profile": DemandProfile(
            (DemandPeriod(0, 60, 12), DemandPeriod(60, 120, 30))
        ),
        "start_s": 0,
        "end_s": 60,
        "transfer_fractions": {"bonaventure": 0.25, "edouard-montpetit": 0.75},
    }
    arguments.update(overrides)
    return generator.generate(**arguments)


class FixedCounts:
    """Record the demand passed to the RNG without sampling the batch size."""

    def __init__(self, count):
        self.count = count
        self.means = []

    def poisson(self, mean):
        self.means.append(mean)
        return self.count


def generator_with_count(monkeypatch, count=3, *, id_prefix="passenger"):
    manager = StreamManager(42)
    counts = FixedCounts(count)
    get_stream = manager.get_stream

    def stream(name):
        return counts if name == "group_sizes" else get_stream(name)

    monkeypatch.setattr(manager, "get_stream", stream)
    return PassengerGenerator(manager, id_prefix=id_prefix), counts


def test_integrated_time_varying_demand_controls_the_poisson_mean(monkeypatch):
    generator, counts = generator_with_count(monkeypatch)
    passengers = generate(generator, start_s=30, end_s=90)

    # 30 seconds at 12/min plus 30 seconds at 30/min gives a Poisson mean of 21.
    assert counts.means == [21]
    assert len(passengers) == 3
    assert all(passenger.origin == "mcgill" for passenger in passengers)
    assert all(passenger.state is PassengerState.CREATED for passenger in passengers)


def test_ids_are_unique_across_batches_and_origins(monkeypatch):
    generator, _ = generator_with_count(monkeypatch)
    first = generate(generator)
    second = generate(
        generator,
        origin="bonaventure",
        transfer_fractions={"mcgill": 1},
    )

    assert [p.passenger_id for p in first + second] == [
        "passenger-000000000001",
        "passenger-000000000002",
        "passenger-000000000003",
        "passenger-000000000004",
        "passenger-000000000005",
        "passenger-000000000006",
    ]
    assert all(p.destination == "mcgill" for p in second)


def test_ids_keep_text_sort_order_across_one_million_passengers(monkeypatch):
    generator, _ = generator_with_count(monkeypatch, count=2)
    # Reach the boundary with four passengers rather than allocating a million.
    monkeypatch.setattr(generator, "_next_id", 999_998)
    first = generate(generator)
    second = generate(generator, start_s=60, end_s=120)
    ids = [passenger.passenger_id for passenger in first + second]

    assert ids == sorted(ids)
    assert ids == [
        "passenger-000000999998",
        "passenger-000000999999",
        "passenger-000001000000",
        "passenger-000001000001",
    ]


def test_zero_share_destinations_are_never_assigned(monkeypatch):
    generator, _ = generator_with_count(monkeypatch, count=10)
    passengers = generate(
        generator,
        transfer_fractions={"bonaventure": 1, "edouard-montpetit": 0},
    )

    assert len(passengers) == 10
    assert {p.destination for p in passengers} == {"bonaventure"}


def test_fractional_shares_control_destination_assignment(monkeypatch):
    generator, _ = generator_with_count(monkeypatch, count=1000)
    destinations = Counter(p.destination for p in generate(generator))

    assert sum(destinations.values()) == 1000
    # At p=0.25 the binomial standard deviation is about 14 passengers.
    # A 50-passenger allowance tolerates sampling noise but rejects a 50/50 split.
    assert destinations["bonaventure"] == pytest.approx(250, rel=0, abs=50)


def test_destination_mapping_order_does_not_change_generated_passengers():
    first = PassengerGenerator(StreamManager(42))
    second = PassengerGenerator(StreamManager(42))

    assert generate(first) == generate(
        second, transfer_fractions={"edouard-montpetit": 0.75, "bonaventure": 0.25}
    )


@pytest.mark.parametrize(
    "overrides,message",
    [
        ({"origin": " "}, "origin"),
        ({"demand_profile": None}, "demand_profile"),
        ({"start_s": -1}, "start_s"),
        ({"transfer_fractions": None}, "transfer_fractions"),
        ({"transfer_fractions": {}}, "transfer_fractions"),
        ({"transfer_fractions": {"mcgill": 1}}, "destination"),
        ({"transfer_fractions": {None: 1}}, "destination"),
        ({"transfer_fractions": {"bonaventure": 0.5}}, "sum to 1"),
        ({"transfer_fractions": {"bonaventure": -0.1}}, "transfer_fractions"),
        ({"transfer_fractions": {"bonaventure": 1.1}}, "transfer_fractions"),
        ({"transfer_fractions": {"bonaventure": math.nan}}, "transfer_fractions"),
        ({"transfer_fractions": {"bonaventure": True}}, "transfer_fractions"),
        ({"transfer_fractions": {"bonaventure": "1"}}, "transfer_fractions"),
    ],
)
def test_invalid_requests_leave_rng_and_ids_unchanged(overrides, message):
    generator = PassengerGenerator(StreamManager(42))

    with pytest.raises(ValueError, match=message):
        generate(generator, **overrides)

    assert generate(generator) == generate(PassengerGenerator(StreamManager(42)))


@pytest.mark.parametrize("prefix", [" ", None])
def test_id_prefix_must_be_a_nonempty_string(prefix):
    with pytest.raises(ValueError, match="id_prefix"):
        PassengerGenerator(StreamManager(42), id_prefix=prefix)


def test_distinct_prefixes_separate_multiple_generators(monkeypatch):
    rem, _ = generator_with_count(monkeypatch, count=1, id_prefix="rem")
    metro, _ = generator_with_count(monkeypatch, count=1, id_prefix="metro")
    first = generate(rem)
    second = generate(metro)

    assert first[0].passenger_id == "rem-000000000001"
    assert second[0].passenger_id == "metro-000000000001"


def test_zero_demand_consumes_neither_ids_nor_random_draws():
    generator = PassengerGenerator(StreamManager(42))

    assert generate(generator, demand_profile=DemandProfile()) == []
    assert generate(generator, start_s=60, end_s=60) == []
    assert generate(generator) == generate(PassengerGenerator(StreamManager(42)))


def test_a_zero_poisson_draw_returns_an_empty_batch_without_spending_ids(monkeypatch):
    generator, counts = generator_with_count(monkeypatch, count=0)

    assert generate(generator) == []
    assert counts.means == [12]

    counts.count = 1
    assert generate(generator)[0].passenger_id == "passenger-000000000001"


def test_an_expected_count_beyond_sampler_limits_is_rejected_without_rng_changes():
    generator = PassengerGenerator(StreamManager(42))
    excessive = DemandProfile((DemandPeriod(0, 60, 1e20),))

    with pytest.raises(ValueError, match="too large to sample"):
        generate(generator, demand_profile=excessive)

    assert generate(generator) == generate(PassengerGenerator(StreamManager(42)))


def test_destination_draws_do_not_change_group_sizes():
    streams = StreamManager(42)
    streams.get_stream("destinations").random(100)

    assert len(generate(PassengerGenerator(streams))) == len(
        generate(PassengerGenerator(StreamManager(42)))
    )


@pytest.mark.parametrize(
    "name", ["walking_times", "run_times", "disruptions", "loads", "prediction_errors"]
)
def test_generation_does_not_change_other_random_sources(name):
    streams = StreamManager(42)
    generate(PassengerGenerator(streams))

    np.testing.assert_array_equal(
        streams.get_stream(name).random(10),
        StreamManager(42).get_stream(name).random(10),
    )


def test_new_stream_preserves_existing_stream_indices():
    assert STREAM_NAMES[:6] == (
        "walking_times",
        "group_sizes",
        "run_times",
        "disruptions",
        "loads",
        "prediction_errors",
    )
    assert STREAM_NAMES[6] == "destinations"


@given(
    seed=st.integers(min_value=0, max_value=2**32 - 1),
    share=st.integers(min_value=0, max_value=100),
)
def test_generated_passengers_are_valid_and_reproducible(seed, share):
    fractions = {"bonaventure": share / 100, "edouard-montpetit": 1 - share / 100}
    first_generator = PassengerGenerator(StreamManager(seed))
    second_generator = PassengerGenerator(StreamManager(seed))
    first = generate(first_generator, transfer_fractions=fractions) + generate(
        first_generator, start_s=60, end_s=120, transfer_fractions=fractions
    )
    second = generate(second_generator, transfer_fractions=fractions) + generate(
        second_generator, start_s=60, end_s=120, transfer_fractions=fractions
    )

    assert first == second
    assert len({p.passenger_id for p in first}) == len(first)
    assert all(p.origin == "mcgill" and p.destination in fractions for p in first)
    assert all(p.state is PassengerState.CREATED for p in first)
