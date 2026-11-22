# AI contribution: 50% or more AI-generated
# AI contribution: 50% or more AI-generated
"""Capture path validation applies before the benchmark starts any work.

The CLI checks its output root, and direct Python callers must retain that
boundary too. This test exercises the failure path without timing a simulation.
"""

import pytest

from scripts.benchmark_simulation import measure


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
