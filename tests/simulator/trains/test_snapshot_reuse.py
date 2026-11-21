# AI contribution: 50% or more AI-generated
"""Snapshot reuse must still reflect every live train-state change.

Only immutable values may be shared. A changed load, delay or next stop must
produce the current values while previously returned snapshots remain frozen.
"""

from simulator.trains.train import ScheduledStop, Train
from simulator.trains.train_component import TrainComponent


def test_reused_train_snapshots_track_live_load_and_delay():
    """A prior snapshot cannot hide passenger boarding or propagated delay."""
    train = Train("A", 800, (ScheduledStop("S", "P", 100, 130),), onboard_load=300)
    component = TrainComponent([train])
    [first] = component.train_states()
    assert component.train_states() == (first,)
    train.onboard_load = 350
    train.current_delay = 10.0
    [updated] = component.train_states()
    assert updated.onboard_load == 350
    assert updated.predicted_arrival_s == 110.0
    assert first.onboard_load == 300
    assert first.predicted_arrival_s == 100.0
