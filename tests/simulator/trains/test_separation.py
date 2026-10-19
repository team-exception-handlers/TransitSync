# AI contribution: 50% or more AI-generated

import pytest

from simulator.trains.separation import (
    TrainMovement,
    enforce_minimum_gap,
)


def test_minimum_gap_without_delay():
    movements = [
        TrainMovement("A", 0),
        TrainMovement("B", 90),
        TrainMovement("C", 180),
    ]

    results = enforce_minimum_gap(movements, 90)

    assert [r.actual_s for r in results] == [0, 90, 180]


def test_recursive_delay_propagation():
    movements = [
        TrainMovement("A", 0, generated_delay_s=60),
        TrainMovement("B", 90),
        TrainMovement("C", 180),
    ]

    results = enforce_minimum_gap(movements, 90)

    assert [r.actual_s for r in results] == [60, 150, 240]

    assert [r.generated_delay_s for r in results] == [60, 0, 0]

    assert [r.inherited_delay_s for r in results] == [0, 60, 60]


def test_delay_does_not_propagate_unnecessarily():
    movements = [
        TrainMovement("A", 0, generated_delay_s=30),
        TrainMovement("B", 150),
        TrainMovement("C", 300),
    ]

    results = enforce_minimum_gap(movements, 90)

    assert results[1].inherited_delay_s == 0
    assert results[2].inherited_delay_s == 0


def test_generated_and_inherited_delay_are_separate():
    movements = [
        TrainMovement("A", 0, generated_delay_s=60),
        TrainMovement("B", 90, generated_delay_s=20),
    ]

    results = enforce_minimum_gap(movements, 90)

    assert results[1].actual_s == 150
    assert results[1].generated_delay_s == 20
    assert results[1].inherited_delay_s == 40
    assert results[1].total_delay_s == 60


def test_minimum_gap_always_holds():
    movements = [
        TrainMovement("A", 0, 120),
        TrainMovement("B", 90, 0),
        TrainMovement("C", 180, 30),
        TrainMovement("D", 270, 0),
    ]

    minimum_gap_s = 90
    results = enforce_minimum_gap(movements, minimum_gap_s)

    for previous, current in zip(results, results[1:], strict=False):
        assert current.actual_s - previous.actual_s >= minimum_gap_s


def test_invalid_gap():
    with pytest.raises(ValueError):
        enforce_minimum_gap([TrainMovement("A", 0)], minimum_gap_s=0)
