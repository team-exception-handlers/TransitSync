# AI contribution: 50% or more AI-generated
import pytest

from simulator.engine.events import PassengerArrival
from simulator.passengers.platform_queue import PlatformQueue
from simulator.trains.train import ScheduledStop, Train


def test_queue_retains_overflow_and_respects_existing_load():
    queue = PlatformQueue(("P",))
    for index in range(3):
        queue.arrive(
            PassengerArrival(
                time_s=index, passenger_id=str(index), group_id="g", platform_id="P"
            )
        )
    train = Train("t", 3, (ScheduledStop("A", "P", 10, 20),), onboard_load=2)
    assert queue.board("P", train) == ["0"]
    assert queue.waiting_count("P") == 2
    assert train.onboard_load == 3
    assert queue.board("P", train) == []


def test_queue_rejects_duplicate_passengers_and_ignores_unowned_platforms():
    queue = PlatformQueue(("P",))
    arrival = PassengerArrival(
        time_s=0, passenger_id="p", group_id="g", platform_id="P"
    )
    assert queue.arrive(arrival)
    with pytest.raises(ValueError, match="Duplicate"):
        queue.arrive(arrival)
    assert not queue.arrive(
        PassengerArrival(time_s=0, passenger_id="q", group_id="g", platform_id="other")
    )
