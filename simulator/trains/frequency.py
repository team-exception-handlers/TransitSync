# AI contribution: 50% or more AI-generated
"""Re-time one metro line to an even headway chosen by the user (#259).

Train frequency is given as a headway h: the time in seconds between one
train and the next at the connecting platform. The GTFS timetable gives the
real, slightly uneven spacing. When a user sets h, the connecting line's
trips are replaced by copies of its first trip, one every h seconds, so the
platform sees exactly the requested service.

Copies are used because a shorter headway needs more trains than the
timetable has, and a longer one fewer. REM trains keep their timetable.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import replace

from simulator.trains.train import ScheduledStop, Train


def retime_line(
    trains: Sequence[Train],
    platform_id: str,
    headway_s: float,
    duration_s: float,
) -> list[Train]:
    """Return ``trains`` with every train serving ``platform_id`` re-spaced.

    Inputs: the built trains, the connecting platform, the headway h and the
    run length, both in seconds. The first train to depart that platform is
    the template. Copy k departs it at ``t0 + k * h`` for every such time
    inside the run, so the copies are ``ceil((duration_s - t0) / h)`` trains.
    Copies keep the template's capacity, line and onboard load, and get the
    ID ``<template id>:h<k>`` so event logs stay readable and unique.

    Trains that never call at the platform are returned unchanged, in their
    original order, before the copies. Raises ``ValueError`` for a headway that
    is not positive or a platform no train serves.
    """
    if not math.isfinite(headway_s) or headway_s <= 0:
        raise ValueError("headway_s must be a positive number of seconds")
    departures = {
        train.id: departure
        for train in trains
        if (departure := _departure_at(train, platform_id)) is not None
    }
    if not departures:
        raise ValueError(f"No train serves platform {platform_id}")
    # Earliest departure wins; equal times keep the first train in the list
    template = min(
        (train for train in trains if train.id in departures),
        key=lambda train: departures[train.id],
    )
    copies = math.ceil((duration_s - departures[template.id]) / headway_s)
    others = [train for train in trains if train.id not in departures]
    return others + [
        _shifted_copy(template, index, index * headway_s)
        # At least the template itself, even if it leaves after the run ends
        for index in range(max(1, copies))
    ]


def _departure_at(train: Train, platform_id: str) -> float | None:
    """Scheduled departure in seconds from ``platform_id``, or None if absent."""
    for stop in train.schedule:
        if stop.platform_id == platform_id:
            return stop.departure_s
    return None


def _shifted_copy(template: Train, index: int, offset_s: float) -> Train:
    """Build copy ``index`` of ``template`` with every stop ``offset_s`` later."""
    schedule: tuple[ScheduledStop, ...] = tuple(
        replace(
            stop,
            arrival_s=stop.arrival_s + offset_s,
            departure_s=stop.departure_s + offset_s,
        )
        for stop in template.schedule
    )
    return Train(
        id=f"{template.id}:h{index}",
        capacity=template.capacity,
        schedule=schedule,
        onboard_load=template.onboard_load,
        line_id=template.line_id,
    )
