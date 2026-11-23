# AI contribution: 50% or more AI-generated
"""Benchmark checks that hold before any simulation is timed.

The CLI checks its output root, and direct Python callers must retain that
boundary too. These tests exercise failure paths without timing a simulation.
"""

import pytest

import scripts.benchmark_simulation as benchmark
from scripts.benchmark_simulation import _installed_version, measure


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
