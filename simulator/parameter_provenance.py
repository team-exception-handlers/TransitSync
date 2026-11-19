# AI contribution: 50% or more AI-generated
"""Parameter provenance loading and validation (US-7.1, #315, #316)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

ConfidenceClassification = Literal["measured", "estimated", "published", "assumed"]

VALID_CLASSIFICATIONS = {"measured", "estimated", "published", "assumed"}

PROVENANCE_PATH = (
    Path(__file__).resolve().parents[1] / "config" / "parameter_provenance.json"
)


@dataclass(frozen=True)
class ParameterProvenanceEntry:
    classification: ConfidenceClassification
    source_name: str
    source_link: str = ""

    def __post_init__(self) -> None:
        if self.classification not in VALID_CLASSIFICATIONS:
            raise ValueError(
                f"Invalid confidence classification: '{self.classification}'. "
                f"Must be one of {VALID_CLASSIFICATIONS}."
            )
        if not isinstance(self.source_name, str) or not self.source_name.strip():
            raise ValueError("source_name must be a non-empty string")
        if not isinstance(self.source_link, str):
            raise ValueError("source_link must be a string")


def load_parameter_provenance(
    filepath: Path | str = PROVENANCE_PATH,
) -> dict[str, ParameterProvenanceEntry]:
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"Parameter provenance file not found: {path}")

    with path.open("r", encoding="utf-8") as f:
        raw_data = json.load(f)

    provenance_map: dict[str, ParameterProvenanceEntry] = {}
    for key, value in raw_data.items():
        if not isinstance(value, dict):
            raise ValueError(f"Provenance entry for '{key}' must be a dictionary")

        provenance_map[key] = ParameterProvenanceEntry(
            classification=value.get("classification"),
            source_name=value.get("source_name", ""),
            source_link=value.get("source_link", ""),
        )
    return provenance_map
