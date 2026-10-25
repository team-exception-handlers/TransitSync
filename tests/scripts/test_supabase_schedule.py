# AI contribution: 50% or more AI-generated
"""Verify schedule extraction using a mocked Supabase connection."""

from datetime import date
from unittest.mock import MagicMock

import psycopg
import pytest

from scripts import supabase_schedule as reader
from scripts.gtfs_calendar import WEEKDAYS
from simulator.timetable import Platform

DAY = date(2026, 10, 5)
PLATFORM = Platform(
    platform_id="rem-mcgill-1",
    interchange_id="mcgill",
    line_id="rem",
    direction_id=1,
    direction_label="Brossard",
    stop_id="MCG",
    stop_name="McGill",
    route_ids=("S1",),
)


@pytest.fixture
def mapping_root(tmp_path, monkeypatch):
    monkeypatch.setattr(reader, "MAPPING_ROOT", tmp_path)
    return tmp_path


def connect_database(monkeypatch, *, empty=False):
    connection = MagicMock()
    connection.__enter__.return_value = connection
    feed = dict(
        feed_id="rem",
        agency="REM",
        feed_version="v1",
        downloaded_on=date(2026, 10, 12),
        feed_start_date=date(2026, 6, 15),
        feed_end_date=date(2026, 10, 25),
    )
    calendar = dict(
        feed_id="rem",
        service_id="daily",
        start_date=date(2026, 6, 15),
        end_date=date(2026, 10, 25),
        **dict.fromkeys(WEEKDAYS, 1),
    )
    rows = {
        "gtfs.feeds": [feed],
        "gtfs.calendar_dates": [],
        "gtfs.calendar": [calendar],
        "gtfs.routes": [dict(feed_id="rem", route_id="S1", route_type=0)],
        "gtfs.stops": [
            dict(
                feed_id="rem",
                stop_id=s,
                stop_name=s if s != "MCG" else "McGill",
                location_type=0,
            )
            for s in ("UP", "MCG", "DOWN")
        ],
        "gtfs.trips": []
        if empty
        else [
            dict(
                feed_id="rem",
                trip_id="t",
                service_id="daily",
                route_id="S1",
                direction_id=1,
                trip_headsign="Brossard",
            )
        ],
        "gtfs.stop_times": [
            dict(
                feed_id="rem",
                trip_id="t",
                stop_id=s,
                stop_sequence=i,
                arrival_s=100 * i,
                departure_s=100 * i + 30,
                pickup_type=0,
                drop_off_type=0,
            )
            for i, s in enumerate(("UP", "MCG", "DOWN"), 1)
        ],
        "gtfs.frequencies": [],
    }

    def execute(query, params=None):
        result = MagicMock()
        for table, data in rows.items():
            if f"FROM {table} " in query:
                result.fetchone.return_value = data[0] if data else None
                result.fetchall.return_value = data
                break
        return result

    connection.execute.side_effect = execute
    connect = MagicMock(return_value=connection)
    monkeypatch.setattr("scripts.supabase_connection.psycopg.connect", connect)
    monkeypatch.setenv("SUPABASE_DB_URL", "postgresql://example.invalid/test")
    monkeypatch.delenv("SUPABASE_SSL_ROOT_CERT", raising=False)
    return connection, connect, rows


@pytest.mark.parametrize("certificate", [None, "/configured/ca.crt"])
def test_reader_flows_native_rows_through_calendar_and_complete_trip_extraction(
    monkeypatch,
    certificate,
):
    connection, connect, _ = connect_database(monkeypatch)
    if certificate is not None:
        monkeypatch.setenv("SUPABASE_SSL_ROOT_CERT", certificate)
    result = reader.read_daily_schedule({"rem": (PLATFORM,)}, DAY)
    assert result["service_date"] == "2026-10-05"
    assert result["feeds"][0]["feed_version"] == "v1"
    assert result["feeds"][0]["service_ids"] == ["daily"]
    visit = result["trips"][0]["visits"][0]
    assert visit["has_earlier_boarding"] and visit["has_later_alighting"]
    assert visit["boarding_allowed"] and visit["alighting_allowed"]
    assert (visit["arrival_s"], visit["departure_s"]) == (200, 230)
    assert connect.call_count == 1
    assert connection.read_only is True
    assert connection.isolation_level == psycopg.IsolationLevel.REPEATABLE_READ
    assert connect.call_args.kwargs["sslmode"] == "verify-full"
    assert connect.call_args.kwargs["connect_timeout"] == 10
    assert connect.call_args.kwargs["sslrootcert"] == (certificate or "system")
    assert connect.call_args.kwargs["prepare_threshold"] is None
    assert connection.__exit__.called
    for call in connection.execute.call_args_list:
        query = call.args[0]
        if "FROM gtfs." in query:
            assert "feed_id = %s" in query
            assert "rem" in call.args[1]
            assert "rem" not in query


def test_no_active_services_rejects_extraction_with_feed_and_date(monkeypatch):
    _, _, rows = connect_database(monkeypatch)
    rows["gtfs.calendar"] = []
    with pytest.raises(ValueError, match="feed 'rem'.*2026-10-05.*no active services"):
        reader.read_daily_schedule({"rem": (PLATFORM,)}, DAY)


def test_missing_trip_stop_times_are_rejected(monkeypatch):
    _, _, rows = connect_database(monkeypatch)
    rows["gtfs.stop_times"] = []
    with pytest.raises(ValueError, match="stop_times"):
        reader.read_daily_schedule({"rem": (PLATFORM,)}, DAY)


def test_unknown_feed_out_of_coverage_and_frequencies_fail(monkeypatch):
    _, _, rows = connect_database(monkeypatch)
    with pytest.raises(ValueError, match="coverage"):
        reader.read_daily_schedule({"rem": (PLATFORM,)}, date(2027, 1, 1))
    rows["gtfs.feeds"] = []
    with pytest.raises(ValueError, match="feed_id"):
        reader.read_daily_schedule({"rem": (PLATFORM,)}, DAY)
    _, _, rows = connect_database(monkeypatch)
    rows["gtfs.frequencies"] = [dict(trip_id="t")]
    with pytest.raises(ValueError, match="frequencies"):
        reader.read_daily_schedule({"rem": (PLATFORM,)}, DAY)


def test_database_failure_does_not_expose_private_diagnostics(monkeypatch):
    _, connect, _ = connect_database(monkeypatch)
    connect.side_effect = psycopg.OperationalError("PRIVATE_CONNECTION_DETAIL")
    with pytest.raises(reader.SupabaseReadError) as caught:
        reader.read_daily_schedule({"rem": (PLATFORM,)}, DAY)
    assert "PRIVATE_CONNECTION_DETAIL" not in str(caught.value)


@pytest.mark.usefixtures("mapping_root")
def test_cli_produces_json_and_safe_errors(monkeypatch, capsys, tmp_path):
    import json
    from dataclasses import asdict

    mapping = tmp_path / "mapping.json"
    mapping.write_text(json.dumps({"rem": [asdict(PLATFORM)]}))
    connect_database(monkeypatch)
    monkeypatch.setattr(reader, "_load_local_connection_settings", lambda: None)
    assert reader.main(["--mapping", str(mapping), "--date", "2026-10-05"]) == 0
    assert json.loads(capsys.readouterr().out)["trips"][0]["trip_id"] == "t"
    assert (
        reader.main(["--mapping", str(tmp_path / "absent"), "--date", "2026-10-05"])
        == 1
    )
    assert "Traceback" not in capsys.readouterr().err


def test_committed_mapping_covers_all_three_interchanges_and_separates_directions():
    mappings = reader.load_mapping(reader.DEFAULT_MAPPING)
    assert set(mappings) == {"rem_20260520", "stm_20260805110000_26S"}
    platforms = [p for group in mappings.values() for p in group]
    assert len(platforms) == len({p.platform_id for p in platforms}) == 12
    assert {p.interchange_id for p in platforms} == {
        "mcgill",
        "gare_centrale_bonaventure",
        "edouard_montpetit",
    }
    metro = mappings["stm_20260805110000_26S"]
    assert len({p.stop_id for p in metro}) == 3
    assert len({(p.stop_id, p.direction_id) for p in metro}) == 6


@pytest.mark.parametrize(
    "content",
    [
        "null",
        "{}",
        '{"$comment":"only a comment"}',
        '{"rem":[]}',
        '{"rem":[{"route_ids":"S1"}]}',
        '{"rem":[null]}',
    ],
)
def test_invalid_mapping_fails_without_database_access(mapping_root, content):
    mapping = mapping_root / "mapping.json"
    mapping.write_text(content)
    with pytest.raises(ValueError, match="mapping"):
        reader.load_mapping(mapping)


def test_repeated_daily_extraction_is_identical_and_source_settings_are_not_saved(
    monkeypatch,
):
    import json

    connect_database(monkeypatch)
    first = reader.read_daily_schedule({"rem": (PLATFORM,)}, DAY)
    second = reader.read_daily_schedule({"rem": (PLATFORM,)}, DAY)
    encoded = json.dumps(first, sort_keys=True)
    assert encoded == json.dumps(second, sort_keys=True)
    assert "postgresql" not in encoded and "SUPABASE_DB_URL" not in encoded


@pytest.mark.parametrize(
    "row,message",
    [
        (None, "route_ids must be a list"),
        ({"route_ids": "S1"}, "route_ids must be a list"),
        ({"route_ids": ["S1"]}, "invalid platform fields"),
        ({"route_ids": ["S1"], "unknown": 1}, "invalid platform fields"),
    ],
)
def test_invalid_platform_row_names_the_feed(mapping_root, row, message):
    import json

    mapping = mapping_root / "mapping.json"
    mapping.write_text(json.dumps({"rem": [row]}))
    with pytest.raises(ValueError, match=f"mapping 'rem': {message}"):
        reader.load_mapping(mapping)


def test_duplicate_json_fields_do_not_silently_replace_mapping(mapping_root):
    path = mapping_root / "mapping.json"
    path.write_text('{"rem": [], "rem": []}')
    with pytest.raises(ValueError, match="mapping"):
        reader.load_mapping(path)


@pytest.mark.parametrize("relative", ["mapping.json", "config/../mapping.json"])
def test_valid_mapping_outside_root_is_rejected(tmp_path, monkeypatch, relative):
    import json
    from dataclasses import asdict

    monkeypatch.setattr(reader, "MAPPING_ROOT", tmp_path / "config")
    (tmp_path / "config").mkdir()
    (tmp_path / "mapping.json").write_text(json.dumps({"rem": [asdict(PLATFORM)]}))
    with pytest.raises(ValueError, match="mapping must be inside the config/ folder"):
        reader.load_mapping(tmp_path / relative)


def test_both_feeds_share_one_snapshot_and_source_trip_ids_remain_feed_scoped(
    monkeypatch,
):
    from dataclasses import replace

    connection, connect, rows = connect_database(monkeypatch)
    for data in rows.values():
        data.extend(row | {"feed_id": "other"} for row in list(data))
    original_execute = connection.execute.side_effect

    def execute(query, params=None):
        result = original_execute(query, params)
        if "FROM gtfs." in query:
            selected = [
                r for r in result.fetchall() if r.get("feed_id", params[0]) == params[0]
            ]
            result.fetchall.return_value = selected
            result.fetchone.return_value = selected[0] if selected else None
        return result

    connection.execute.side_effect = execute
    other = replace(PLATFORM, platform_id="other-mcgill")
    result = reader.read_daily_schedule({"rem": (PLATFORM,), "other": (other,)}, DAY)
    assert connect.call_count == 1
    assert [(t["feed_id"], t["trip_id"]) for t in result["trips"]] == [
        ("other", "t"),
        ("rem", "t"),
    ]
    assert {v["platform_id"] for t in result["trips"] for v in t["visits"]} == {
        "rem-mcgill-1",
        "other-mcgill",
    }


def test_reference_dates_are_extracted_in_one_snapshot_with_explicit_feed_mapping(
    monkeypatch,
):
    connection, connect, _ = connect_database(monkeypatch)
    dates = (DAY, date(2026, 10, 10), date(2026, 10, 11))
    schedules = reader.read_schedules({"rem": (PLATFORM,)}, dates)
    assert connect.call_count == 1
    assert [s["service_date"] for s in schedules] == [d.isoformat() for d in dates]
    assert all(s["platforms"][0]["feed_id"] == "rem" for s in schedules)
    assert connection.read_only


def test_duplicate_or_invalid_requested_dates_fail_before_connect(monkeypatch):
    _, connect, _ = connect_database(monkeypatch)
    with pytest.raises(ValueError, match="dates"):
        reader.read_schedules({"rem": (PLATFORM,)}, (DAY, DAY))
    assert not connect.called
