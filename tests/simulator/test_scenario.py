# AI contribution: 50% or more AI-generated
"""Scenario validation against saved schedules and Toronto calendar time."""

import json
from dataclasses import replace
from datetime import date

import pytest

from simulator.engine.runner import run_scenario
from simulator.scenario import (
    DatasetMetadata,
    ScenarioValidationError,
    load_scenario_file,
    load_scenario_json,
    resolve_preset,
)


@pytest.fixture
def dataset():
    return DatasetMetadata(
        dataset_id="stm-rem-test",
        coverage_start=date(2026, 8, 24),
        coverage_end=date(2026, 12, 31),
        service_day_end_s_by_interchange={
            "mcgill": 92576,  # 25:42:56
            "gare_centrale_bonaventure": 92695,  # 25:44:55
            "edouard_montpetit": 92720,  # 25:45:20
        },
        interchange_ids=frozenset(
            {"mcgill", "gare_centrale_bonaventure", "edouard_montpetit"}
        ),
    )


def load(dataset, **overrides):
    values = {
        "dataset_id": dataset.dataset_id,
        "date": "2026-10-05",
        "start_time": "07:00",
        "interchanges": ["mcgill"],
    }
    values.update(overrides)
    return load_scenario_json(json.dumps(values), {dataset.dataset_id: dataset})


@pytest.mark.parametrize(
    ("horizon", "start_time"),
    [(92576, "00:50"), (86401, "00:00")],
)
def test_fall_back_rejects_missing_overnight_service(dataset, horizon, start_time):
    # Nov 1 noon is EST: its GTFS origin is 01:00 EDT, not midnight.
    dataset = replace(
        dataset,
        coverage_start=date(2026, 11, 2),
        service_day_end_s_by_interchange={"mcgill": horizon},
    )
    with pytest.raises(ScenarioValidationError, match="2026-11-01"):
        load(dataset, date="2026-11-02", start_time=start_time, duration_s=60)


@pytest.mark.parametrize("horizon", [86400, 84600])
def test_fall_back_accepts_midnight_when_preceding_service_has_ended(dataset, horizon):
    # The origin is 01:00 EDT, but 24 elapsed hours end at midnight EST.
    dataset = replace(
        dataset,
        coverage_start=date(2026, 11, 2),
        service_day_end_s_by_interchange={"mcgill": horizon},
    )
    scenario = load(dataset, date="2026-11-02", start_time="00:00", duration_s=60)
    assert scenario.start_utc.isoformat() == "2026-11-02T05:00:00+00:00"


def test_spring_forward_accepts_exact_overnight_cutoff(dataset):
    # Mar 8 noon is EDT: 25:42:56 ends Mar 9 at 01:42:56 EDT.
    dataset = replace(dataset, coverage_start=date(2026, 3, 9))
    scenario = load(dataset, date="2026-03-09", start_time="01:42:56", duration_s=60)
    assert scenario.start_utc.isoformat() == "2026-03-09T05:42:56+00:00"


def test_rejects_other_timezone_instead_of_reinterpreting_coverage(dataset):
    with pytest.raises(ScenarioValidationError, match="timezone.*America/Toronto"):
        load(dataset, date="2026-08-24", start_time="03:00", timezone="UTC")


@pytest.mark.parametrize("duration", [3600, 3600.0])
def test_oversized_repetitions_return_workload_validation_error(dataset, duration):
    with pytest.raises(ScenarioValidationError, match="duration_s.*repetitions"):
        load(dataset, duration_s=duration, repetitions=10**400)


def test_defaults_and_saved_settings_round_trip(dataset):
    scenario = load(dataset)
    saved = scenario.to_dict()
    assert saved == {
        "dataset_id": "stm-rem-test",
        "date": "2026-10-05",
        "start_time": "07:00:00",
        "duration_s": 3600,
        "repetitions": 1,
        "master_seed": 42,
        "interchanges": ["mcgill"],
        "timezone": "America/Toronto",
        "dst_fold": None,
        "resolved_start_utc": "2026-10-05T11:00:00+00:00",
        "resolved_start_utc_offset": "-04:00",
    }
    assert (
        load_scenario_json(json.dumps(saved), {dataset.dataset_id: dataset}) == scenario
    )


def test_explicit_toronto_timezone_matches_default(dataset):
    assert load(dataset, timezone="America/Toronto") == load(dataset)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("duration_s", 0),
        ("duration_s", -1),
        ("duration_s", True),
        ("duration_s", "3600"),
        ("duration_s", None),
        ("duration_s", float("inf")),
        ("duration_s", float("nan")),
        ("repetitions", 0),
        ("repetitions", 1.5),
        ("repetitions", True),
        ("repetitions", None),
        ("master_seed", -1),
        ("master_seed", False),
        ("date", "2026-02-30"),
        ("date", None),
        ("start_time", "24:00"),
        ("start_time", "07:00-04:00"),
        ("start_time", None),
        ("timezone", None),
        ("timezone", "America/Vancouver"),
        ("dst_fold", True),
        ("dst_fold", 1),  # Only meaningful at an ambiguous start time.
        ("dataset_id", "missing-version"),
        ("interchanges", []),
        ("interchanges", ["mcgill", "mcgill"]),
        ("interchanges", ["unknown"]),
        ("interchanges", [42]),
        ("resolved_start_utc", "2026-10-05T12:00:00+00:00"),
        ("resolved_start_utc_offset", "-05:00"),
    ],
)
def test_invalid_values_name_the_field_instead_of_using_defaults(dataset, field, value):
    with pytest.raises(ScenarioValidationError, match=field):
        load(dataset, **{field: value})


def test_unknown_field_suggests_correction(dataset):
    with pytest.raises(
        ScenarioValidationError, match="duration.*did you mean 'duration_s'"
    ):
        load(dataset, duration=120)


@pytest.mark.parametrize("content", ["{", "[]", "null", '"scenario"'])
def test_rejects_malformed_json_or_non_object(content, dataset):
    with pytest.raises(ScenarioValidationError, match="scenario"):
        load_scenario_json(content, {dataset.dataset_id: dataset})


def test_loads_saved_scenario_file(dataset, tmp_path):
    scenario = load(dataset)
    path = tmp_path / "scenario.json"
    path.write_text(json.dumps(scenario.to_dict()), encoding="utf-8")
    assert load_scenario_file(path, {dataset.dataset_id: dataset}) == scenario


def test_missing_scenario_file_returns_clear_validation_error(dataset, tmp_path):
    with pytest.raises(ScenarioValidationError, match="could not read scenario file"):
        load_scenario_file(tmp_path / "missing.json", {dataset.dataset_id: dataset})


@pytest.mark.parametrize("content", [b"\xff", "{}".encode("utf-16")])
def test_invalid_file_encoding_returns_clear_validation_error(
    dataset, tmp_path, content
):
    path = tmp_path / "scenario.json"
    path.write_bytes(content)
    with pytest.raises(ScenarioValidationError, match="scenario file.*UTF-8") as caught:
        load_scenario_file(path, {dataset.dataset_id: dataset})
    assert str(path) in str(caught.value)


@pytest.mark.parametrize(
    ("duration", "repetitions"), [(3600, 100), (3600.0, 100), (0.1, 3_600_000)]
)
def test_accepts_workload_exactly_at_limit(dataset, duration, repetitions):
    scenario = load(dataset, duration_s=duration, repetitions=repetitions)
    assert scenario.duration_s == duration
    assert scenario.repetitions == repetitions


@pytest.mark.parametrize(("duration", "repetitions"), [(3600, 101), (360000.000001, 1)])
def test_rejects_workload_over_limit(dataset, duration, repetitions):
    with pytest.raises(ScenarioValidationError, match="100 simulated hours"):
        load(dataset, duration_s=duration, repetitions=repetitions)


def test_tiny_duration_with_large_repetitions_is_checked_without_overflow(dataset):
    # ~1 total second, although the repetition count cannot be converted to float.
    scenario = load(dataset, duration_s=1e-320, repetitions=10**320)
    assert scenario.repetitions == 10**320


@pytest.mark.parametrize("day", ["2026-08-23", "2027-01-01"])
def test_rejects_dates_outside_coverage(dataset, day):
    with pytest.raises(ScenarioValidationError, match="outside dataset coverage"):
        load(dataset, date=day)


def test_allows_crossing_midnight_within_coverage(dataset):
    scenario = load(dataset, date="2026-10-05", start_time="23:30", duration_s=3600)
    assert scenario.duration_s == 3600


def test_rejects_crossing_midnight_beyond_coverage(dataset):
    with pytest.raises(ScenarioValidationError, match="outside dataset coverage"):
        load(dataset, date="2026-12-31", start_time="23:30", duration_s=3600)


def test_before_overnight_cutoff_names_missing_service_date(dataset):
    with pytest.raises(ScenarioValidationError, match="2026-08-23"):
        load(dataset, date="2026-08-24", start_time="01:42:55", duration_s=60)


def test_accepts_exact_overnight_cutoff(dataset):
    scenario = load(dataset, date="2026-08-24", start_time="01:42:56", duration_s=60)
    assert scenario.start_time.isoformat() == "01:42:56"


def test_coverage_uses_only_selected_interchanges(dataset):
    scenario = load(dataset, date="2026-08-24", start_time="01:43", duration_s=60)
    assert scenario.interchanges == ("mcgill",)
    with pytest.raises(ScenarioValidationError, match="2026-08-23"):
        load(
            dataset,
            date="2026-08-24",
            start_time="01:43",
            duration_s=60,
            interchanges=["mcgill", "edouard_montpetit"],
        )


def test_overnight_service_from_covered_previous_date_is_available(dataset):
    scenario = load(dataset, date="2026-08-25", start_time="01:00", duration_s=60)
    assert scenario.service_date == date(2026, 8, 25)


def test_rejects_interchange_missing_from_dataset(dataset):
    dataset = replace(dataset, interchange_ids=frozenset({"edouard_montpetit"}))
    with pytest.raises(ScenarioValidationError, match="mcgill.*not in dataset"):
        load(dataset)


@pytest.mark.parametrize("horizon", [None, True, -1, float("inf")])
def test_requires_valid_horizon_for_selected_interchange(dataset, horizon):
    dataset = replace(dataset, service_day_end_s_by_interchange={"mcgill": horizon})
    with pytest.raises(
        ScenarioValidationError, match="service_day_end_s_by_interchange"
    ):
        load(dataset)


def test_spring_forward_rejects_nonexistent_start(dataset):
    dataset = replace(dataset, coverage_start=date(2026, 3, 1))
    with pytest.raises(ScenarioValidationError, match="start_time.*does not exist"):
        load(dataset, date="2026-03-08", start_time="02:30")


@pytest.mark.parametrize(
    ("fold", "utc", "offset"),
    [
        (0, "2026-11-01T05:30:00+00:00", "-04:00"),
        (1, "2026-11-01T06:30:00+00:00", "-05:00"),
    ],
)
def test_fall_back_choices_have_distinct_instants_and_round_trip(
    dataset, fold, utc, offset
):
    scenario = load(dataset, date="2026-11-01", start_time="01:30", dst_fold=fold)
    assert scenario.start_utc.isoformat() == utc
    saved = scenario.to_dict()
    assert saved["resolved_start_utc_offset"] == offset
    assert (
        load_scenario_json(json.dumps(saved), {dataset.dataset_id: dataset}) == scenario
    )


def test_fall_back_requires_explicit_fold(dataset):
    with pytest.raises(ScenarioValidationError, match="dst_fold.*occurs twice"):
        load(dataset, date="2026-11-01", start_time="01:30")


def test_fall_back_exact_overnight_cutoff_is_available(dataset):
    dataset = replace(dataset, coverage_start=date(2026, 11, 2))
    scenario = load(dataset, date="2026-11-02", start_time="01:42:56", duration_s=60)
    assert scenario.start_utc.isoformat() == "2026-11-02T06:42:56+00:00"


def test_elapsed_duration_across_fall_back_stays_within_25_hour_day(dataset):
    dataset = replace(dataset, coverage_end=date(2026, 11, 1))
    scenario = load(dataset, date="2026-11-01", start_time="00:30", duration_s=86400)
    assert scenario.duration_s == 86400


@pytest.mark.parametrize(
    ("name", "expected_date", "start"),
    [
        ("weekday_morning", date(2026, 10, 5), "07:00:00"),
        ("weekday_afternoon", date(2026, 10, 5), "16:00:00"),
        ("saturday_morning", date(2026, 10, 10), "10:00:00"),
        ("sunday_morning", date(2026, 10, 11), "10:00:00"),
    ],
)
def test_presets_choose_matching_saved_service_dates(
    dataset, name, expected_date, start
):
    dataset = replace(
        dataset,
        service_dates=(date(2026, 10, 5), date(2026, 10, 10), date(2026, 10, 11)),
    )
    scenario = resolve_preset(name, dataset)
    assert scenario.service_date == expected_date
    assert scenario.start_time.isoformat() == start
    assert scenario.duration_s == 3600
    assert scenario.interchanges == ("mcgill",)


def test_preset_settings_are_editable(dataset):
    scenario = resolve_preset(
        "weekday_morning",
        dataset,
        interchanges=("edouard_montpetit",),
        overrides={"date": "2026-10-06", "start_time": "08:00", "duration_s": 120},
    )
    assert scenario.service_date == date(2026, 10, 6)
    assert scenario.start_time.isoformat() == "08:00:00"
    assert scenario.duration_s == 120
    assert scenario.interchanges == ("edouard_montpetit",)


def test_rejects_invalid_preset_override(dataset):
    with pytest.raises(ScenarioValidationError, match="duration_s"):
        resolve_preset("weekday_morning", dataset, overrides={"duration_s": 0})


def test_rejects_unknown_preset(dataset):
    with pytest.raises(ScenarioValidationError, match="preset.*unknown"):
        resolve_preset("holiday", dataset)


def test_rejects_preset_without_representative_date(dataset):
    with pytest.raises(ScenarioValidationError, match="no date for this preset"):
        resolve_preset("sunday_morning", replace(dataset, service_dates=()))


def test_loaded_scenario_runs_reproducibly_with_existing_runner(
    dataset, tmp_path, build_streams, build_tiny_network
):
    scenario = load(dataset, duration_s=600, master_seed=123)
    first = run_scenario(
        scenario, build_streams, build_tiny_network, tmp_path / "first"
    )
    second = run_scenario(
        scenario, build_streams, build_tiny_network, tmp_path / "second"
    )
    assert first.summary.master_seed == 123
    assert first.summary.duration_s == 600
    assert first.summary.events_processed > 0
    assert first.events_path.read_bytes() == second.events_path.read_bytes()
    assert first.summary_path.read_bytes() == second.summary_path.read_bytes()
