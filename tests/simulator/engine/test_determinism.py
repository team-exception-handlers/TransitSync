"""Test simulation determinism and manifest integration (US-1.1, #10 and #11)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pytest

from simulator.engine.events import TrainArrival
from simulator.engine.runner import RunError, run_scenario


@dataclass
class DummyScenario:
    duration_s: float
    master_seed: int
    gtfs_version: str = "test-gtfs-v1"
    parameters: dict | None = None


class DummyComponent:
    def start(self, scheduler) -> None:
        """Schedule a real event so the event log and summary are non-empty."""
        scheduler.schedule(
            TrainArrival(
                time_s=10.0,
                train_id="train-1",
                station_id="station-1",
                platform_id="platform-1",
                scheduled_s=10.0,
                disruption_delay_s=0.0,
            )
        )

    def handle(self, event, scheduler) -> None:
        """Handle a scheduled event."""
        pass


def build_streams(seed: int) -> object:
    """Return a placeholder random stream object for testing."""
    return object()


def build_components(scenario: object, streams: object) -> list:
    """Return the dummy component used by the tests."""
    return [DummyComponent()]


def test_scenario_determinism(tmp_path: Path) -> None:
    """Identical scenarios produce identical logs and summaries."""
    scenario = DummyScenario(
        duration_s=300.0,
        master_seed=123,
        parameters={"rate": 2.0},
    )

    first = run_scenario(
        scenario,
        build_streams,
        build_components,
        tmp_path / "run-1",
    )
    second = run_scenario(
        scenario,
        build_streams,
        build_components,
        tmp_path / "run-2",
    )

    # Event logs and summaries must match byte-for-byte.
    assert first.events_path.read_bytes() == second.events_path.read_bytes()
    assert first.summary_path.read_bytes() == second.summary_path.read_bytes()

    # Verify that both runs actually processed the scheduled event.
    assert first.summary.events_processed == 1
    assert second.summary.events_processed == 1

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
            build_streams,
            build_components,
            output_dir,
        )

    # The original manifest must remain untouched.
    assert manifest_path.read_text(encoding="utf-8") == original_manifest

    # No other run outputs should have been created.
    assert not (output_dir / "events.jsonl").exists()
    assert not (output_dir / "summary.json").exists()
