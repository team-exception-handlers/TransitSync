# AI contribution: 50% or more AI-generated
"""Load and validate reproducible simulation scenarios."""

from __future__ import annotations

import difflib
import json
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

WORKLOAD_LIMIT_HOURS = 100
DEFAULT_TIMEZONE = "America/Toronto"
PRESET_SETTINGS: dict[str, dict[str, Any]] = {
    "weekday_morning": {"start_time": "07:00:00", "duration_s": 3600},
    "weekday_afternoon": {"start_time": "16:00:00", "duration_s": 3600},
    "saturday_morning": {"start_time": "10:00:00", "duration_s": 3600},
    "sunday_morning": {"start_time": "10:00:00", "duration_s": 3600},
}
INTERCHANGE_IDS = frozenset(
    {"gare_centrale_bonaventure", "mcgill", "edouard_montpetit"}
)
SCENARIO_FIELDS = frozenset(
    {
        "dataset_id",
        "date",
        "start_time",
        "duration_s",
        "repetitions",
        "master_seed",
        "interchanges",
        "timezone",
        "dst_fold",
        "resolved_start_utc",
        "resolved_start_utc_offset",
    }
)


class ScenarioValidationError(ValueError):
    """A scenario input is missing, malformed, or outside its allowed range."""


@dataclass(frozen=True)
class DatasetMetadata:
    """Small dataset boundary used for scenario coverage and interchange checks."""

    dataset_id: str
    coverage_start: date
    coverage_end: date
    service_day_end_s_by_interchange: Mapping[str, int | float]
    interchange_ids: frozenset[str]
    service_dates: tuple[date, ...] | None = None


@dataclass(frozen=True)
class Scenario:
    """Validated settings for one experiment and its complete repetitions."""

    dataset_id: str
    service_date: date
    start_time: time
    duration_s: int | float
    repetitions: int
    master_seed: int
    interchanges: tuple[str, ...]
    timezone: str
    dst_fold: int | None
    resolved_start: datetime

    @property
    def start_utc(self) -> datetime:
        """Return the resolved local start as an unambiguous UTC instant."""
        return self.resolved_start.astimezone(UTC)

    def to_dict(self) -> dict[str, Any]:
        """Return canonical JSON-compatible settings, including resolved offset."""
        return {
            "dataset_id": self.dataset_id,
            "date": self.service_date.isoformat(),
            "start_time": self.start_time.isoformat(),
            "duration_s": self.duration_s,
            "repetitions": self.repetitions,
            "master_seed": self.master_seed,
            "interchanges": list(self.interchanges),
            "timezone": self.timezone,
            "dst_fold": self.dst_fold,
            "resolved_start_utc": self.start_utc.isoformat(),
            "resolved_start_utc_offset": _offset_text(self.resolved_start),
        }


def load_scenario_json(content: str, datasets: dict[str, DatasetMetadata]) -> Scenario:
    """Parse and validate a JSON scenario against available dataset metadata."""
    try:
        values = json.loads(content)
    except json.JSONDecodeError as error:
        raise ScenarioValidationError(
            f"scenario JSON is invalid at line {error.lineno}, column {error.colno}"
        ) from error
    except ValueError as error:
        raise ScenarioValidationError(
            "scenario JSON contains an integer with too many digits"
        ) from error
    if not isinstance(values, dict):
        raise ScenarioValidationError("scenario must be a JSON object")
    return _scenario_from_mapping(values, datasets)


def load_scenario_file(path: Path, datasets: dict[str, DatasetMetadata]) -> Scenario:
    """Read a UTF-8 JSON scenario file and validate its contents."""
    try:
        content = path.read_text(encoding="utf-8")
    except UnicodeError as error:
        raise ScenarioValidationError(
            f"scenario file must use UTF-8 encoding: {path}"
        ) from error
    except OSError as error:
        raise ScenarioValidationError(
            f"could not read scenario file: {path}"
        ) from error
    return load_scenario_json(content, datasets)


def resolve_preset(
    name: str,
    dataset: DatasetMetadata,
    *,
    interchanges: tuple[str, ...] | None = None,
    overrides: dict[str, Any] | None = None,
) -> Scenario:
    """Fill a named preset, then validate it like any other scenario."""
    if name not in PRESET_SETTINGS:
        choices = ", ".join(sorted(PRESET_SETTINGS))
        raise ScenarioValidationError(
            f"preset: unknown name {name!r}; choose {choices}"
        )
    weekday = {
        "weekday_morning": {0, 1, 2, 3, 4},
        "weekday_afternoon": {0, 1, 2, 3, 4},
        "saturday_morning": {5},
        "sunday_morning": {6},
    }[name]
    preset = PRESET_SETTINGS[name]
    values: dict[str, Any] = {
        "dataset_id": dataset.dataset_id,
        "date": _representative_date(dataset, weekday).isoformat(),
        "start_time": preset["start_time"],
        "duration_s": preset["duration_s"],
        "repetitions": 1,
        "master_seed": 42,
        "interchanges": list(("mcgill",) if interchanges is None else interchanges),
        "timezone": DEFAULT_TIMEZONE,
    }
    if overrides:
        values.update(overrides)
    return _scenario_from_mapping(values, {dataset.dataset_id: dataset})


def _scenario_from_mapping(
    values: dict[str, Any], datasets: dict[str, DatasetMetadata]
) -> Scenario:
    _reject_unknown_fields(values)
    dataset = _select_dataset(values, datasets)
    service_date = _parse_date(values.get("date"))
    start_time = _parse_time(values.get("start_time"))
    duration_s = _positive_duration(values.get("duration_s", 3600))
    repetitions = _positive_integer(values.get("repetitions", 1), "repetitions")
    master_seed = _nonnegative_integer(values.get("master_seed", 42), "master_seed")
    interchanges = _parse_interchanges(values.get("interchanges"), dataset)
    timezone = _parse_timezone(values.get("timezone", DEFAULT_TIMEZONE))
    dst_fold = _parse_fold(values.get("dst_fold"))
    try:
        resolved_start = _resolve_local_start(
            service_date, start_time, timezone, dst_fold
        )
        _check_saved_resolution(values, resolved_start)
        _check_workload(duration_s, repetitions)
        _check_coverage(dataset, resolved_start, duration_s, interchanges)
    except OverflowError as error:
        raise ScenarioValidationError(
            "date: requested simulation window exceeds the supported date range"
        ) from error
    return Scenario(
        dataset_id=dataset.dataset_id,
        service_date=service_date,
        start_time=start_time,
        duration_s=duration_s,
        repetitions=repetitions,
        master_seed=master_seed,
        interchanges=interchanges,
        timezone=timezone.key,
        dst_fold=dst_fold,
        resolved_start=resolved_start,
    )


def _reject_unknown_fields(values: dict[str, Any]) -> None:
    unknown = sorted(values.keys() - SCENARIO_FIELDS)
    if unknown:
        name = unknown[0]
        suggestion = difflib.get_close_matches(name, SCENARIO_FIELDS, n=1)
        hint = f"; did you mean {suggestion[0]!r}?" if suggestion else ""
        raise ScenarioValidationError(f"{name}: unknown field{hint}")


def _select_dataset(
    values: dict[str, Any], datasets: dict[str, DatasetMetadata]
) -> DatasetMetadata:
    dataset_id = values.get("dataset_id")
    if not isinstance(dataset_id, str) or not dataset_id:
        raise ScenarioValidationError("dataset_id: a dataset ID is required")
    try:
        return datasets[dataset_id]
    except KeyError as error:
        raise ScenarioValidationError(
            f"dataset_id: dataset {dataset_id!r} is unavailable"
        ) from error


def _parse_date(value: Any) -> date:
    if not isinstance(value, str):
        raise ScenarioValidationError("date: expected YYYY-MM-DD")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as error:
        raise ScenarioValidationError(
            "date: expected a valid YYYY-MM-DD date"
        ) from error
    if parsed.isoformat() != value:
        raise ScenarioValidationError("date: expected a valid YYYY-MM-DD date")
    return parsed


def _parse_time(value: Any) -> time:
    if not isinstance(value, str):
        raise ScenarioValidationError("start_time: expected a local time such as 07:00")
    try:
        parsed = time.fromisoformat(value)
    except ValueError as error:
        raise ScenarioValidationError(
            "start_time: expected a valid local time"
        ) from error
    if parsed.tzinfo is not None:
        raise ScenarioValidationError(
            "start_time: provide local time without an offset"
        )
    if (
        re.fullmatch(r"(?:[01]?\d|2[0-3]):[0-5]\d(?::[0-5]\d(?:\.\d{1,6})?)?", value)
        is None
    ):
        raise ScenarioValidationError("start_time: expected a valid local time")
    return parsed


def _positive_duration(value: Any) -> int | float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ScenarioValidationError(
            "duration_s: expected a positive number of seconds"
        )
    try:
        finite = math.isfinite(value)
    except OverflowError:
        finite = False
    if not finite or value <= 0:
        raise ScenarioValidationError(
            "duration_s: must be finite and greater than zero"
        )
    return value


def _positive_integer(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ScenarioValidationError(f"{field}: expected a whole number of at least 1")
    return value


def _nonnegative_integer(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ScenarioValidationError(f"{field}: expected a non-negative whole number")
    return value


def _parse_interchanges(value: Any, dataset: DatasetMetadata) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise ScenarioValidationError("interchanges: select at least one interchange")
    if any(not isinstance(item, str) for item in value):
        raise ScenarioValidationError(
            "interchanges: each selection must be a string ID"
        )
    selected = set(value)
    if len(value) != len(selected):
        raise ScenarioValidationError(
            "interchanges: duplicate selections are not allowed"
        )
    unknown = sorted(selected - INTERCHANGE_IDS)
    if unknown:
        raise ScenarioValidationError(
            f"interchanges: unknown identifier {unknown[0]!r}"
        )
    unavailable = sorted(selected - dataset.interchange_ids)
    if unavailable:
        raise ScenarioValidationError(
            f"interchanges: {unavailable[0]!r} is not in dataset {dataset.dataset_id!r}"
        )
    return tuple(value)


def _parse_timezone(value: Any) -> ZoneInfo:
    if value != DEFAULT_TIMEZONE:
        raise ScenarioValidationError(
            f"timezone: must be {DEFAULT_TIMEZONE!r} for TransitSync scenarios"
        )
    return ZoneInfo(DEFAULT_TIMEZONE)


def _parse_fold(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value not in (0, 1):
        raise ScenarioValidationError(
            "dst_fold: choose 0 or 1 for a repeated local time"
        )
    return value


def _resolve_local_start(
    service_date: date, start_time: time, timezone: ZoneInfo, dst_fold: int | None
) -> datetime:
    local = datetime.combine(service_date, start_time)
    candidates: dict[datetime, datetime] = {}
    for fold in (0, 1):
        attached = local.replace(tzinfo=timezone, fold=fold)
        utc_start = attached.astimezone(UTC)
        round_trip = utc_start.astimezone(timezone)
        if round_trip.replace(tzinfo=None) == local:
            candidates[utc_start] = round_trip
    if not candidates:
        raise ScenarioValidationError(
            "start_time: this local time does not exist because of a clock change"
        )
    if len(candidates) == 2:
        if dst_fold is None:
            raise ScenarioValidationError(
                "dst_fold: this local time occurs twice; choose 0 for the first "
                "occurrence or 1 for the second"
            )
        chosen = next(value for value in candidates.values() if value.fold == dst_fold)
        return chosen
    if dst_fold is not None:
        raise ScenarioValidationError(
            "dst_fold: only provide this for a repeated local time"
        )
    return next(iter(candidates.values()))


def _check_saved_resolution(values: dict[str, Any], resolved: datetime) -> None:
    expected = {
        "resolved_start_utc": resolved.astimezone(UTC).isoformat(),
        "resolved_start_utc_offset": _offset_text(resolved),
    }
    for field, actual in expected.items():
        saved = values.get(field)
        if saved is not None and saved != actual:
            raise ScenarioValidationError(
                f"{field}: saved value does not match the resolved local start"
            )


def _check_workload(duration_s: int | float, repetitions: int) -> None:
    limit_s = WORKLOAD_LIMIT_HOURS * 3600
    try:
        exceeds_limit = duration_s * repetitions > limit_s
    except OverflowError:
        # A float cannot multiply an enormous integer, even when the duration
        # is tiny. Compare its exact ratio using arbitrary-precision integers.
        numerator, denominator = duration_s.as_integer_ratio()
        exceeds_limit = numerator * repetitions > limit_s * denominator
    if exceeds_limit:
        raise ScenarioValidationError(
            "duration_s: duration_s / 3600 × repetitions must be at most "
            f"{WORKLOAD_LIMIT_HOURS} simulated hours"
        )


def _check_coverage(
    dataset: DatasetMetadata,
    resolved_start: datetime,
    duration_s: int | float,
    interchanges: tuple[str, ...],
) -> None:
    horizons = dataset.service_day_end_s_by_interchange
    if not isinstance(horizons, Mapping):
        raise ScenarioValidationError(
            "dataset.service_day_end_s_by_interchange: expected an interchange map"
        )
    service_day_end_s = max(
        _service_day_end(horizons, interchange) for interchange in interchanges
    )
    start_date = resolved_start.date()
    start_utc = resolved_start.astimezone(UTC)
    end_utc = start_utc + timedelta(seconds=duration_s)
    end_date = end_utc.astimezone(resolved_start.tzinfo).date()
    if start_date < dataset.coverage_start or end_date > dataset.coverage_end:
        raise ScenarioValidationError(
            "date: requested simulation window is outside dataset coverage "
            f"{dataset.coverage_start.isoformat()} through "
            f"{dataset.coverage_end.isoformat()}"
        )
    try:
        preceding_service_date = dataset.coverage_start - timedelta(days=1)
    except OverflowError:
        return
    try:
        preceding_service_start = _gtfs_service_start_utc(preceding_service_date)
        preceding_service_end = preceding_service_start + timedelta(
            seconds=service_day_end_s
        )
    except OverflowError as error:
        raise ScenarioValidationError(
            "dataset.service_day_end_s_by_interchange: value is too large"
        ) from error
    if preceding_service_start < end_utc and preceding_service_end > start_utc:
        raise ScenarioValidationError(
            "date: requested simulation window overlaps overnight service "
            f"from {preceding_service_date.isoformat()}, before dataset "
            f"coverage starts {dataset.coverage_start.isoformat()}"
        )


def _gtfs_service_start_utc(service_date: date) -> datetime:
    """Resolve GTFS's local-noon-minus-12-elapsed-hours time origin in Toronto."""
    # https://gtfs.org/documentation/schedule/reference/#field-types
    noon = datetime.combine(
        service_date, time(12), tzinfo=ZoneInfo(DEFAULT_TIMEZONE)
    ).astimezone(UTC)
    return noon - timedelta(hours=12)


def _service_day_end(horizons: Mapping[str, int | float], interchange: str) -> float:
    """Return a validated service horizon for one selected interchange."""
    value = horizons.get(interchange)
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ScenarioValidationError(
            "dataset.service_day_end_s_by_interchange: missing or invalid value "
            f"for interchange {interchange!r}"
        )
    try:
        is_finite = math.isfinite(value)
    except OverflowError:
        is_finite = False
    if not is_finite or value < 0:
        raise ScenarioValidationError(
            "dataset.service_day_end_s_by_interchange: expected a finite, "
            f"non-negative value for interchange {interchange!r}"
        )
    return float(value)


def _representative_date(dataset: DatasetMetadata, weekdays: set[int]) -> date:
    midpoint = (
        dataset.coverage_start + (dataset.coverage_end - dataset.coverage_start) / 2
    )
    if dataset.service_dates is None:
        days = (dataset.coverage_end - dataset.coverage_start).days + 1
        candidates = (
            dataset.coverage_start + timedelta(days=offset) for offset in range(days)
        )
    else:
        candidates = iter(dataset.service_dates)
    try:
        return min(
            (
                item
                for item in candidates
                if item.weekday() in weekdays
                and dataset.coverage_start <= item <= dataset.coverage_end
            ),
            key=lambda item: (abs((item - midpoint).days), item),
        )
    except ValueError as error:
        raise ScenarioValidationError(
            f"dataset_id: dataset {dataset.dataset_id!r} has no date for this preset"
        ) from error


def _offset_text(value: datetime) -> str:
    offset = value.utcoffset()
    if offset is None:
        raise ScenarioValidationError("start_time: could not resolve a UTC offset")
    total_minutes = int(offset.total_seconds() // 60)
    sign = "+" if total_minutes >= 0 else "-"
    hours, minutes = divmod(abs(total_minutes), 60)
    return f"{sign}{hours:02d}:{minutes:02d}"
