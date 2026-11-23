# AI contribution: 50% or more AI-generated
"""Benchmark guards and scenario overrides without running simulations.

The CLI checks its output root, and direct Python callers must retain that
boundary too. These tests exercise failures and record inputs with a fake runner.
"""

from dataclasses import replace
from datetime import time
from types import SimpleNamespace

import pytest

import scripts.benchmark_simulation as benchmark
from scripts.benchmark_simulation import _installed_version, measure


@pytest.fixture
def recorded_scenario(monkeypatch):
    """Record benchmark inputs with nonzero clock fields and empty run outputs.

    Component construction still supplies the API's real response adapter, but
    no scheduled event is executed, including for the full service day.
    """
    recorded = {}
    service = benchmark.simulation_run.SimulationRunService
    original_load = service._load_scenario

    def load(instance, *args, **kwargs):
        original = original_load(instance, *args, **kwargs)
        scenario = replace(
            original,
            start_time=time(7, 30, 45, 123456),
            resolved_start=original.resolved_start.replace(
                hour=7, minute=30, second=45, microsecond=123456
            ),
        )
        recorded["source"] = scenario
        recorded["service_end_s"] = instance._dataset.service_day_end_s_by_interchange[
            scenario.interchanges[0]
        ]
        return scenario

    def run(scenario, stream_factory, component_factory, output_dir):
        recorded["run"] = scenario
        component_factory(scenario, stream_factory(scenario.master_seed))
        events = output_dir / "events.jsonl"
        decisions = output_dir / "decisions.jsonl"
        events.write_text("", encoding="utf-8")
        decisions.write_text("", encoding="utf-8")
        return SimpleNamespace(events_path=events, decisions_path=decisions)

    monkeypatch.setattr(service, "_load_scenario", load)
    monkeypatch.setattr(benchmark.simulation_run, "run_scenario", run)
    return recorded


@pytest.mark.parametrize("full_day", [False, True], ids=["hour", "full-day"])
def test_benchmark_clock_and_duration_override(recorded_scenario, full_day):
    """Midnight resets every clock field; ordinary runs retain their settings."""
    result = measure("no_control", full_day=full_day)
    source, actual = recorded_scenario["source"], recorded_scenario["run"]
    expected_clock = time() if full_day else source.start_time
    expected_duration = recorded_scenario["service_end_s"] if full_day else 3600
    assert actual.start_time == expected_clock
    assert actual.resolved_start.time() == expected_clock
    assert actual.resolved_start.date() == source.resolved_start.date()
    assert actual.resolved_start.tzinfo is source.resolved_start.tzinfo
    assert actual.duration_s == expected_duration
    assert result["duration_s"] == expected_duration
    assert source.duration_s == 3600
    assert recorded_scenario["service_end_s"] > 86400


def test_capture_cannot_escape_the_repository_root(tmp_path, monkeypatch):
    """A sibling path must fail before creating artifacts or starting the API."""
    root = tmp_path / "workspace"
    root.mkdir()
    monkeypatch.chdir(root)
    capture = tmp_path / "outside"
    with pytest.raises(ValueError, match="capture must be inside the repository"):
        measure("no_control", capture=capture)
    assert not capture.exists()


def test_comparison_cannot_report_an_ignored_parameter_as_an_uncached_update():
    """Comparison normalizes baseline sliders, so changed bounds apply to /run."""
    with pytest.raises(
        ValueError, match="comparison measurements require fresh settings"
    ):
        measure("no_control", compare=True, changed=True)


def test_missing_optional_package_is_recorded_as_none():
    """Measurement metadata names a missing package instead of failing."""
    assert _installed_version("transitsync-no-such-package") is None
    assert _installed_version("numpy")


def test_fingerprint_includes_runtime_json_and_excludes_ignored_artifacts(
    tmp_path, monkeypatch
):
    """A duration or network change must invalidate a benchmark's identity."""
    monkeypatch.chdir(tmp_path)
    config = tmp_path / "config" / "scenarios" / "mcgill.json"
    config.parent.mkdir(parents=True)
    config.write_text('{"duration_s":3600}')

    def git(arguments, **kwargs):
        if arguments[1] == "ls-files":
            return b"config/scenarios/mcgill.json\0"
        return "fixed-head" if kwargs.get("text") else b""

    monkeypatch.setattr(benchmark.subprocess, "check_output", git)
    before = benchmark.source_metadata()["source_sha256"]
    config.write_text('{"duration_s":92576}')
    after = benchmark.source_metadata()["source_sha256"]
    assert before != after
    ignored = tmp_path / ".benchmarks" / "result.json"
    ignored.parent.mkdir()
    ignored.write_text('{"request_s":42}')
    assert benchmark.source_metadata()["source_sha256"] == after


def test_fingerprint_never_reads_environment_files_under_config(tmp_path, monkeypatch):
    """Even explicitly listed environment files stay outside benchmark metadata."""
    monkeypatch.chdir(tmp_path)
    secret = tmp_path / "config" / ".env"
    secret.parent.mkdir()
    secret.write_text("EXAMPLE=value")

    def git(arguments, **kwargs):
        if arguments[1] == "ls-files":
            return b"config/.env\0"
        return "fixed-head" if kwargs.get("text") else b""

    monkeypatch.setattr(benchmark.subprocess, "check_output", git)
    before = benchmark.source_metadata()["source_sha256"]
    secret.write_text("EXAMPLE=changed")
    assert benchmark.source_metadata()["source_sha256"] == before
