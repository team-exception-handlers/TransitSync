# AI contribution: 50% or more AI-generated
"""Prototype tests for keyed prediction errors (LLL spike #191).

Each test is one point of the spike's Definition of Done. The paired-run
tests also run the current sequential model, which fails as in #193, so the
same test shows the drift before and its absence after. Draws are compared
as e, the error divided by kappa * sigma, because a hold changes the horizon
and so sigma, but must not change the random part.
"""

import os
import statistics
import subprocess
import sys
import time
import timeit
from pathlib import Path
from types import SimpleNamespace

import pytest
from hypothesis import given
from hypothesis import strategies as st

from simulator.control.decision import DecisionPipeline
from simulator.control.interface import (
    DecisionController,
    HoldAction,
    ObservationSnapshot,
    TrainState,
)
from simulator.control.keyed_draws import KeyedPredictionErrorModel, keyed_normal
from simulator.control.prediction_error import (
    PredictionErrorModel,
    PredictionErrorSettings,
    arrival_sigma_s,
)
from simulator.engine.random_streams import StreamManager
from simulator.engine.runner import run_scenario
from simulator.trains.train import ScheduledStop, Train
from simulator.trains.train_component import TrainComponent

SEED = 7
HOLD_S = 120.0
# Chosen so that kappa 0.5 and 1 hold train A at different stops
DUE_WITHIN_S = 90.0
REPO_ROOT = Path(__file__).resolve().parents[3]


class HoldTrainA(DecisionController):
    """Holds train A at its stops; with ``due_within_s``, only when it sees
    another train due that soon, so the holds depend on the estimates."""

    name = "hold_train_a"

    def __init__(self, hold_s, due_within_s=None):
        self.hold_s = hold_s
        self.due_within_s = due_within_s
        # Platforms where train A was held, to check that two runs differ
        self.held_at = []

    def evaluate(self, observation):
        """Return a hold for train A only; every other train leaves on time."""
        if not self.hold_s or observation.train_id != "A":
            return ()
        if self.due_within_s is not None and not any(
            train.predicted_arrival_s is not None
            and train.predicted_arrival_s - observation.time_s < self.due_within_s
            for train in observation.trains
            if train.train_id != "A"
        ):
            return ()
        self.held_at.append(observation.platform_id)
        return (HoldAction("A", self.hold_s, "test hold"),)


class Recording:
    """Wraps an error model and keeps each arrival draw e by prediction."""

    def __init__(self, model):
        self.model = model
        self.draws = {}

    def apply(self, truth):
        """Pass ``truth`` through the model, keeping e for each arrival."""
        seen = self.model.apply(truth)
        kappa = self.model.settings.arrival_kappa
        for true_train, seen_train in zip(truth.trains, seen.trains, strict=True):
            if true_train.predicted_arrival_s is None:
                continue
            sigma = arrival_sigma_s(true_train.predicted_arrival_s - truth.time_s)
            error_s = seen_train.predicted_arrival_s - true_train.predicted_arrival_s
            # Dividing by kappa * sigma leaves e, which a hold or kappa must not change
            # A hold never changes a scheduled departure, so both runs share keys
            decision = (truth.train_id, truth.platform_id, truth.scheduled_departure_s)
            self.draws[(*decision, true_train.train_id)] = error_s / (kappa * sigma)
        return seen


def make_trains():
    # Four trains 150 s apart, each calling at three stops 200 s apart
    return [
        Train(
            name,
            800,
            tuple(
                ScheduledStop(f"S{k}", f"P{k}", start + 200 * k, start + 200 * k + 30)
                for k in range(3)
            ),
        )
        for name, start in zip("ABCD", range(100, 700, 150), strict=True)
    ]


def run_draws(output_dir, model, controller):
    """Run the scenario once; return the arrival draws the model gave."""
    recording = Recording(model)
    decision = DecisionPipeline(controller, error_model=recording)
    # Each run needs its own folder: the runner refuses one that holds output
    run_scenario(
        SimpleNamespace(master_seed=SEED, duration_s=2000.0),
        lambda _seed: None,
        lambda _scenario, _streams: [TrainComponent(make_trains(), decision=decision)],
        output_dir,
    )
    return recording.draws


def sequential(settings):
    """The current model from #187: one shared stream, in decision order."""
    return PredictionErrorModel(
        settings, StreamManager(SEED).get_stream("prediction_errors")
    )


def keyed(settings):
    """The prototype: each draw keyed by what is predicted."""
    return KeyedPredictionErrorModel(settings, SEED)


# Strict: if the sequential model ever passes, the setup no longer shows drift
MODELS = [
    pytest.param(
        sequential,
        id="sequential",
        marks=pytest.mark.xfail(strict=True, reason="draws follow decision order"),
    ),
    pytest.param(keyed, id="keyed"),
]


@pytest.mark.parametrize("make_model", MODELS)
def test_same_draw_with_and_without_holds(tmp_path, make_model):
    # DoD 1: train A held 120 s at every stop in one run of the pair only
    settings = PredictionErrorSettings()
    plain = run_draws(tmp_path / "plain", make_model(settings), HoldTrainA(0))
    held = run_draws(tmp_path / "held", make_model(settings), HoldTrainA(HOLD_S))
    # Every prediction of the plain run also happens in the held run, so
    # every draw can be compared one to one
    assert len(plain) > 10
    assert plain.keys() <= held.keys()
    assert {key: held[key] for key in plain} == pytest.approx(plain)


@pytest.mark.parametrize("make_model", MODELS)
def test_same_draw_at_two_kappas(tmp_path, make_model):
    # DoD 1: the holds read the estimates, so kappa changes where train A holds
    runs = {}
    for kappa in (0.5, 1.0):
        controller = HoldTrainA(HOLD_S, due_within_s=DUE_WITHIN_S)
        model = make_model(PredictionErrorSettings(arrival_kappa=kappa))
        draws = run_draws(tmp_path / str(kappa), model, controller)
        runs[kappa] = (controller.held_at, draws)
    (held_half, half), (held_full, full) = runs.values()
    # Guard: if both runs held at the same stops, the test would prove nothing
    assert held_half != held_full
    # Different holds change which predictions exist; compare the shared ones
    common = half.keys() & full.keys()
    assert len(common) > 10
    assert {key: full[key] for key in common} == pytest.approx(
        {key: half[key] for key in common}
    )


def snapshot(train_ids):
    # Every train is due at P2 at 220 s, 120 s ahead of the decision at 100 s
    trains = tuple(
        TrainState(train_id, "rem", "P2", 220.0, 230.0, 0.0, 300, 780)
        for train_id in train_ids
    )
    return ObservationSnapshot(100.0, "A", "S1", "P1", 130.0, trains, (), ())


def estimates(train_ids):
    """Estimated arrival and load for each train, from the keyed model."""
    seen = KeyedPredictionErrorModel(PredictionErrorSettings(), SEED).apply(
        snapshot(train_ids)
    )
    return {t.train_id: (t.predicted_arrival_s, t.onboard_load) for t in seen.trains}


# Short unique IDs, so Hypothesis also tries IDs that share letters
train_ids = st.lists(
    st.text("ABCDEFGH", min_size=1, max_size=3), max_size=6, unique=True
)


@given(ids=train_ids, others=train_ids, data=st.data())
def test_estimate_ignores_order_and_other_trains(ids, others, data):
    # DoD 2: shuffle the trains and add others in between; estimates stay put
    # Others never reuse an ID from ids, so each train stays one prediction
    mixed = data.draw(st.permutations(ids + [i for i in others if i not in ids]))
    seen = estimates(mixed)
    assert {train_id: seen[train_id] for train_id in ids} == estimates(ids)


def test_same_draws_whatever_the_python_hash_seed():
    # DoD 3: separate processes with different PYTHONHASHSEED values
    code = (
        "from simulator.control.keyed_draws import keyed_normal;"
        "print([keyed_normal(7, 'A', 'P1', 130.0, 'arrival', t) for t in 'ABCD'],"
        " hash('A'))"
    )
    # Each child process gets its own hash seed, like two separate runs
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
    # hash() does change, so a key built on it would break the pairing
    assert hash_1 != hash_2
    assert draws_1 == draws_2


def test_draws_are_standard_normal():
    # DoD 4: mean within 0.03 of 0 and SD within 0.03 of 1 over 10,000 keys
    # One key per draw, as in a run where every prediction has its own key
    draws = [keyed_normal(SEED, "train", i) for i in range(10_000)]
    assert abs(statistics.fmean(draws)) < 0.03
    assert abs(statistics.stdev(draws) - 1) < 0.03


def test_100k_draws_take_under_a_second():
    # DoD 5: keeps a full-day run inside the 30 000 ms performance target
    def draw_100k():
        # One draw per call, as the model makes them, not a vectorised batch
        for i in range(100_000):
            keyed_normal(SEED, "A", "P1", 130.0, "arrival", i)

    # CPU time, best of 3: other programs on a busy machine do not count
    timings = timeit.repeat(draw_100k, timer=time.process_time, number=1, repeat=3)
    assert min(timings) < 1.0


def test_int_and_float_keys_give_the_same_draw():
    # A schedule may give 130 or 130.0 for the same departure
    assert keyed_normal(SEED, "A", 130) == keyed_normal(SEED, "A", 130.0)
    # Another master seed is another random scenario
    assert keyed_normal(SEED, "A", 130) != keyed_normal(SEED + 1, "A", 130)


def test_perfect_information_returns_true_values():
    # kappa = 0 still draws, then multiplies the error by 0
    truth = snapshot("AB")
    model = KeyedPredictionErrorModel(PredictionErrorSettings(0, 0, 0), SEED)
    assert model.apply(truth) == truth


@pytest.mark.parametrize("seed", [-1, 2**128, 1.5, True, "7"])
def test_rejects_bad_seed(seed):
    # Negative, too large, or not an int (bool and str included)
    with pytest.raises(ValueError, match="seed"):
        keyed_normal(seed, "A")
