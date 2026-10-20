# AI contribution: 50% or more AI-generated
"""Test simulation determinism and manifest integration (US-1.1, #10 and #11)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pytest

from simulator.engine.events import TrainArrival
from simulator.engine.random_streams import StreamManager
from simulator.engine.runner import RunError, run_scenario

# Number of seeded train arrivals each test run schedules
ARRIVALS = 3


@dataclass
class DummyScenario:
    duration_s: float
    master_seed: int
    gtfs_version: str = "test-gtfs-v1"
    parameters: dict | None = None


class SeededComponent:
    """Schedules train arrivals at times drawn from the ``run_times`` stream.

    The arrival times depend only on the master seed, so the event log changes
    when the seed changes and repeats exactly when it does not.
    """

    def __init__(self, streams: StreamManager) -> None:
        self._rng = streams.get_stream("run_times")

    def start(self, scheduler) -> None:
        for index, time_s in enumerate(self._rng.uniform(10.0, 290.0, ARRIVALS)):
            scheduler.schedule(
                TrainArrival(
                    time_s=float(time_s),
                    train_id=f"train-{index}",
                    station_id="station-1",
                    platform_id="platform-1",
                    scheduled_s=float(time_s),
                    disruption_delay_s=0.0,
                )
            )

    def handle(self, event, scheduler) -> None:
        """No follow-up events: the seeded arrivals are all this test needs."""


def build_components(scenario: object, streams: StreamManager) -> list:
    """Return the seeded component used by the tests."""
    return [SeededComponent(streams)]


def _run(tmp_path: Path, name: str, master_seed: int):
    return run_scenario(
        DummyScenario(duration_s=300.0, master_seed=master_seed),
        StreamManager,
        build_components,
        tmp_path / name,
    )


def test_scenario_determinism(tmp_path: Path) -> None:
    """Identical scenarios produce identical logs and summaries."""
    scenario = DummyScenario(
        duration_s=300.0,
        master_seed=123,
        parameters={"rate": 2.0},
    )

    first = run_scenario(
        scenario,
        StreamManager,
        build_components,
        tmp_path / "run-1",
    )
    second = run_scenario(
        scenario,
        StreamManager,
        build_components,
        tmp_path / "run-2",
    )

    # Event logs and summaries must match byte-for-byte.
    assert first.events_path.read_bytes() == second.events_path.read_bytes()
    assert first.summary_path.read_bytes() == second.summary_path.read_bytes()

    # Verify that both runs actually processed the seeded arrivals.
    assert first.summary.events_processed == ARRIVALS
    assert second.summary.events_processed == ARRIVALS

    # Read and validate both manifests.
    first_manifest = json.loads(first.manifest_path.read_text(encoding="utf-8"))
    second_manifest = json.loads(second.manifest_path.read_text(encoding="utf-8"))

    assert first_manifest["timestamp"]
    assert second_manifest["timestamp"]
    assert first_manifest["master_seed"] == 123
    assert first_manifest["duration_s"] == 300.0
    assert first_manifest["gtfs_version"] == "test-gtfs-v1"
    assert first_manifest["parameters"] == {"rate": 2.0}

    # Timestamps may differ, but the other manifest fields should match.
    first_manifest.pop("timestamp")
    second_manifest.pop("timestamp")
    assert first_manifest == second_manifest


def _arrival_times(result) -> list[float]:
    lines = result.events_path.read_text(encoding="utf-8").splitlines()
    return sorted(json.loads(line)["time_s"] for line in lines)


def test_different_seed_changes_the_event_log(tmp_path: Path) -> None:
    """A different master seed draws different arrival times."""
    first = _run(tmp_path, "seed-123", master_seed=123)
    other = _run(tmp_path, "seed-124", master_seed=124)

    assert first.events_path.read_bytes() != other.events_path.read_bytes()
    # The change comes from the sampled times, not only from the seed field
    assert _arrival_times(first) != _arrival_times(other)
    assert other.summary.events_processed == ARRIVALS


def test_arrival_times_come_from_the_seeded_stream(tmp_path: Path) -> None:
    """The logged times are the draws from the run_times stream for that seed."""
    expected = StreamManager(123).get_stream("run_times").uniform(10.0, 290.0, ARRIVALS)
    result = _run(tmp_path, "seed-123", master_seed=123)

    assert _arrival_times(result) == sorted(float(time_s) for time_s in expected)
    assert all(10.0 <= time_s < 290.0 for time_s in _arrival_times(result))


def test_existing_manifest_rejects_run(tmp_path: Path) -> None:
    """An existing manifest must not be overwritten by a new run."""
    output_dir = tmp_path / "existing-run"
    output_dir.mkdir()

    manifest_path = output_dir / "manifest.json"
    original_manifest = '{"existing": true}\n'
    manifest_path.write_text(original_manifest, encoding="utf-8")

    with pytest.raises(RunError):
        run_scenario(
            DummyScenario(duration_s=300.0, master_seed=123),
            StreamManager,
            build_components,
            output_dir,
        )

    # The original manifest must remain untouched.
    assert manifest_path.read_text(encoding="utf-8") == original_manifest

    # No other run outputs should have been created.
    assert not (output_dir / "events.jsonl").exists()
    assert not (output_dir / "summary.json").exists()
