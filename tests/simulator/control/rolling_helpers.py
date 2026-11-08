# AI contribution: 50% or more AI-generated
"""Deterministic timetables and a hand-integrable walk for US-2.6 tests."""

from dataclasses import replace

from simulator.control.interface import (
    IncomingTransfer,
    ObservationSnapshot,
    TrainState,
)
from simulator.control.planning import FutureVisit


class UniformWalk:
    """A uniform 0–100 s walk: ten percent finish in any ten-second interval."""

    def cdf(self, t_s):
        return max(0.0, min(1.0, t_s / 100.0))


def visit(train="A", platform="P1", departure=100.0, *, index=0, trip=0):
    return FutureVisit(
        train,
        trip,
        index,
        f"S-{platform}",
        platform,
        departure - 10,
        departure,
        departure - 10,
        departure,
    )


def group(platform="P1", feeder=100.0, count=10, name=None):
    return IncomingTransfer(
        name or f"g-{platform}", platform, count, feeder, feeder + 100, feeder, count
    )


def snapshot(visits=None, groups=None, *, time=100.0, load=10):
    if visits is None:
        visits = (visit(), visit("next", departure=1100))
    if groups is None:
        groups = (group(),)
    trains = tuple(
        TrainState(train, "line", None, None, None, 0, load, 800)
        for train in sorted({v.train_id for v in visits})
    )
    visits = tuple(
        replace(v, arrived=True)
        if v.train_id == "A" and v.trip_index == 0 and v.stop_index == 0
        else v
        for v in visits
    )
    return ObservationSnapshot(
        time, "A", "S-P1", "P1", 100, trains, (), tuple(groups), tuple(visits)
    )
