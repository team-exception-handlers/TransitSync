# AI contribution: 50% or more AI-generated
"""PR #197 regressions for residual queues and repeated recovery (#62)."""

from copy import deepcopy
from dataclasses import FrozenInstanceError, replace

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from simulator.control.break_even import BreakEvenWeights
from simulator.control.decision import DecisionPipeline
from simulator.control.downstream import evaluate_downstream, project_visits
from simulator.engine.event_queue import Scheduler
from simulator.engine.events import Boarding, PassengerArrival
from simulator.passengers.platform_queue import PlatformQueue
from simulator.trains.door_throughput import DoorThroughput
from simulator.trains.suspension import LineSuspension
from simulator.trains.train import ScheduledStop, Train
from simulator.trains.train_component import TrainComponent
from tests.simulator.control.downstream_helpers import forecast
from tests.simulator.control.downstream_run_helpers import CaptureHold, events_for
from tests.simulator.control.rolling_helpers import snapshot, visit


def boarding_case(hold, next_arrival):
    """A boards 10 of 40 queued riders; a following B can take the remainder."""
    queue = PlatformQueue(("P1",))
    trains = [
        Train("A", 800, (ScheduledStop("S", "P1", 100, 110),)),
        Train("B", 800, (ScheduledStop("S", "P1", next_arrival, next_arrival + 10),)),
    ]
    policy = CaptureHold(hold)
    component = TrainComponent(
        trains,
        minimum_gap_s=1,
        passenger_queue=queue,
        rem_door_throughput={"A": DoorThroughput(1, 1)},
        decision=DecisionPipeline(policy),
    )
    scheduler, records = Scheduler(), []
    component.start(scheduler)
    for index in range(40):
        scheduler.schedule(
            PassengerArrival(
                time_s=90, passenger_id=f"p{index}", group_id="g", platform_id="P1"
            )
        )

    def process(event):
        records.append(event)
        component.handle(event, scheduler)

    scheduler.run_until(110, process)
    return component, queue, scheduler, policy.observation, records, process


@pytest.mark.parametrize("next_arrival, expected_cost", [(600, 0), (120, 1200)])
def test_left_behind_queue_is_costed_at_next_train(next_arrival, expected_cost):
    component, queue, scheduler, seen, records, process = boarding_case(
        30, next_arrival
    )
    assert queue.waiting_count("P1") == 30
    assert seen.future_visits[0].arrived is True
    assert seen.trains[0].onboard_load == 10
    # The door budget, rather than total vehicle capacity, prevented boarding.
    assert seen.trains[0].onboard_load < seen.trains[0].capacity
    before = deepcopy((component.trains, component.platform_states(), seen))
    pending, now = scheduler.pending, scheduler.now
    baseline, candidate, cost = forecast(seen, hold=30)
    # B at 600 is unaffected. B at 120 is blocked until just after A leaves
    # at 140: its departure moves 130 -> 150, costing 30 * 20 * 2 = 1200.
    assert cost.waiting_ps == pytest.approx(expected_cost, abs=1e-9)
    assert (component.trains, component.platform_states(), seen) == before
    assert scheduler.pending == pending
    assert scheduler.now == now
    scheduler.run_until(700, process)
    boarded = [e for e in records if isinstance(e, Boarding)]
    assert sum(e.train_id == "A" for e in boarded) == 10
    assert sum(e.train_id == "B" for e in boarded) == 30
    assert queue.waiting_count("P1") == 0
    assert max(e.time_s for e in boarded if e.train_id == "B") == pytest.approx(
        candidate[1].arrival_s, abs=1e-9
    )
    # Advancing live trains must not rewrite any previously returned value.
    assert seen == before[2]
    assert baseline[0].departure_s == 110


def test_distant_following_train_boards_left_behind_riders_at_same_time():
    times = []
    for hold in (0, 30):
        _, _, scheduler, _, records, process = boarding_case(hold, 600)
        scheduler.run_until(700, process)
        times.append(
            [
                (event.passenger_id, event.time_s)
                for event in records
                if isinstance(event, Boarding) and event.train_id == "B"
            ]
        )
    assert times[0] == times[1]
    assert len(times[0]) == 30
    assert {time for _, time in times[0]} == {600}


def recovery_snapshot(slack=12):
    """Four trips with distinct platforms and three recoverable layovers."""
    visits = []
    for trip in range(4):
        origin = visit(
            "A", "P1" if trip == 0 else f"R{trip}", 100 + 200 * trip, trip=trip
        )
        visits.append(replace(origin, recovery_s=slack if trip else 0))
        terminal = visit("A", f"T{trip}", 210 + 200 * trip, trip=trip, index=1)
        if trip < 3:
            terminal = replace(
                terminal,
                departure_s=terminal.arrival_s,
                skips_departure=True,
                can_hold=False,
            )
        visits.append(terminal)
    return snapshot(visits, groups=(), load=100)


@given(hold=st.integers(0, 60), slack=st.integers(1, 20))
@settings(max_examples=30)
def test_multi_trip_recovery_never_creates_extra_onboard_cost(hold, slack):
    seen = recovery_snapshot(slack)
    baseline, candidate, cost = forecast(seen, hold=hold)
    # For a 30 s hold and 12 s layovers, the carried delays are 30,18,6,0.
    # Recovery beyond the remaining delay must not create a negative carry
    # that would be counted as a new positive cost at a subsequent stop.
    delays = [max(0, hold - trip * slack) for trip in range(4)]
    assert [candidate[2 * trip].departure_s for trip in range(4)] == [
        100 + 200 * trip + delays[trip] for trip in range(4)
    ]
    assert cost.onboard_ps == 0
    assert cost.waiting_ps == 0
    assert [p.departure_s for p in baseline] == [100, 200, 300, 400, 500, 600, 700, 810]


@pytest.mark.parametrize("new_delay, expected_cost", [(False, 2000), (True, 4000)])
def test_cost_after_full_recovery_charges_only_new_delay(new_delay, expected_cost):
    seen = recovery_snapshot()
    suspensions = (LineSuspension("line", 105, 130),)
    holds = {("A", 0, 0): 10}
    if new_delay:
        suspensions += (LineSuspension("line", 705, 730),)
        holds[("A", 3, 0)] = 10
    seen = replace(seen, suspensions=suspensions)
    baseline = project_visits(seen, {}, 1000)
    candidate = project_visits(seen, holds, 1000)
    cost = evaluate_downstream(baseline, candidate, seen, BreakEvenWeights(), 1000)
    # Each closure adds 30 s of delay: 10 s is explicit local holding;
    # only 20 s * 100 riders is additional onboard cost. The first 30 s
    # recovers as 18,6,0 across the three 12 s layovers.
    assert [candidate[i].departure_s for i in (1, 3, 5)] == [230, 418, 606]
    assert cost.onboard_ps == expected_cost
    assert cost.waiting_ps == 0


@pytest.mark.parametrize("hold", [0, 10, 30, 36, 40])
def test_multi_trip_forecast_matches_engine_after_recovery(tmp_path, hold):
    seen = recovery_snapshot()
    trips = tuple(
        tuple(
            ScheduledStop(
                "S", v.platform_id, v.scheduled_arrival_s, v.scheduled_departure_s
            )
            for v in seen.future_visits
            if v.trip_index == trip
        )
        for trip in range(4)
    )
    train = Train("A", 800, trips[0], layover_slack=12, return_trips=trips[1:])
    policy = CaptureHold(hold)
    events, _ = events_for(tmp_path, [train], policy)
    projected = project_visits(policy.observation, {("A", 0, 0): hold}, 1000)
    actual = {
        e["platform_id"]: e["time_s"]
        for e in events
        if e["event_type"] == "train_departure"
    }
    assert {
        p.visit.platform_id: p.departure_s
        for p in projected
        if not p.visit.skips_departure
    } == actual
    assert actual["R3"] == 700 + max(0, hold - 36)


def test_projected_visit_and_cost_are_immutable():
    _, candidate, cost = forecast(recovery_snapshot())
    with pytest.raises(FrozenInstanceError):
        candidate[0].departure_s = 0
    with pytest.raises(FrozenInstanceError):
        cost.onboard_ps = 0
