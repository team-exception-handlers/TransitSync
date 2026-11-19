# AI contribution: 50% or more AI-generated
"""Unit tests for parameter provenance loading and validation."""

from pathlib import Path

import pytest

from simulator.parameter_provenance import (
    ParameterProvenanceEntry,
    load_parameter_provenance,
)


def test_valid_provenance_entry() -> None:
    entry = ParameterProvenanceEntry(
        classification="measured",
        source_name="Test Source",
        source_link="https://example.com",
    )
    assert entry.classification == "measured"
    assert entry.source_name == "Test Source"
    assert entry.source_link == "https://example.com"


def test_invalid_classification_raises_error() -> None:
    with pytest.raises(ValueError, match="Invalid confidence classification"):
        ParameterProvenanceEntry(
            classification="unverified",  # type: ignore[arg-type]
            source_name="Bad Source",
        )


def test_empty_source_name_raises_error() -> None:
    with pytest.raises(ValueError, match="source_name must be a non-empty string"):
        ParameterProvenanceEntry(
            classification="published",
            source_name="   ",
        )


def test_load_parameter_provenance_valid_file(tmp_path: Path) -> None:
    config_file = tmp_path / "parameter_provenance.json"
    config_file.write_text(
        '{"test_param": {"classification": "estimated", '
        '"source_name": "Model X", "source_link": ""}}',
        encoding="utf-8",
    )

    result = load_parameter_provenance(config_file)
    assert "test_param" in result
    assert result["test_param"].classification == "estimated"
    assert result["test_param"].source_name == "Model X"


def test_load_parameter_provenance_missing_file() -> None:
    with pytest.raises(FileNotFoundError):
        load_parameter_provenance("nonexistent_file.json")
