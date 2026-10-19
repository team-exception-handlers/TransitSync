# AI contribution: 50% or more AI-generated
"""Test the Supabase reader with in-memory data and mocked connections."""

import os
from datetime import date
from unittest.mock import MagicMock

import psycopg
import pytest

from scripts.supabase_calendar import main, read_active_services


def database(
    monkeypatch,
    *,
    feed=True,
    calendars=(),
    exceptions=(),
    coverage=(date(2026, 6, 15), date(2026, 10, 25)),
):
    connection = MagicMock()
    connection.__enter__.return_value = connection
    # Results for timeout setup, feed metadata, calendars, and exceptions.
    results = [MagicMock(), MagicMock(), MagicMock(), MagicMock()]
    results[1].fetchone.return_value = (
        {"feed_start_date": coverage[0], "feed_end_date": coverage[1]} if feed else None
    )
    results[2].fetchall.return_value = list(calendars)
    results[3].fetchall.return_value = list(exceptions)
    connection.execute.side_effect = results
    connect = MagicMock(return_value=connection)
    monkeypatch.setattr("scripts.supabase_calendar.psycopg.connect", connect)
    monkeypatch.setenv("SUPABASE_DB_URL", "postgresql://example.invalid/test")
    monkeypatch.delenv("SUPABASE_SSL_ROOT_CERT", raising=False)
    return connection, connect


def regular():
    return dict(
        feed_id="rem",
        service_id="weekday",
        monday=1,
        tuesday=1,
        wednesday=1,
        thursday=1,
        friday=1,
        saturday=0,
        sunday=0,
        start_date=date(2026, 6, 15),
        end_date=date(2026, 10, 25),
    )


def test_database_rows_flow_through_real_holiday_selector(monkeypatch):
    exceptions = [
        dict(
            feed_id="rem",
            service_id="weekday",
            date=date(2026, 10, 12),
            exception_type=2,
        ),
        dict(
            feed_id="rem",
            service_id="sunday",
            date=date(2026, 10, 12),
            exception_type=1,
        ),
    ]
    conn, connect = database(monkeypatch, calendars=[regular()], exceptions=exceptions)
    assert read_active_services("rem", date(2026, 10, 12)) == ("sunday",)
    assert conn.read_only is True
    assert conn.isolation_level == psycopg.IsolationLevel.REPEATABLE_READ
    assert connect.call_args.kwargs["sslmode"] == "verify-full"
    assert connect.call_args.kwargs["sslrootcert"] == "system"
    assert connect.call_args.kwargs["connect_timeout"] == 10
    assert conn.__exit__.called


@pytest.mark.parametrize(
    "day,expected",
    [
        (date(2026, 10, 5), ("monday",)),
        (date(2026, 10, 6), ("tuesday",)),
        (date(2026, 10, 7), ("wednesday",)),
        (date(2026, 10, 8), ("thursday",)),
        (date(2026, 10, 9), ("friday",)),
        (date(2026, 10, 10), ("saturday",)),
        (date(2026, 10, 11), ("sunday",)),
    ],
)
def test_native_database_weekday_flags_select_the_expected_day(
    monkeypatch, day, expected
):
    weekdays = (
        "monday",
        "tuesday",
        "wednesday",
        "thursday",
        "friday",
        "saturday",
        "sunday",
    )
    calendars = [
        regular() | dict.fromkeys(weekdays, 0) | {weekday: 1, "service_id": weekday}
        for weekday in weekdays
    ]
    database(monkeypatch, calendars=calendars)
    assert read_active_services("rem", day) == expected


def test_database_holiday_can_use_its_own_single_day_calendar(monkeypatch):
    calendars = [
        regular() | {"feed_id": "stm"},
        regular()
        | {
            "feed_id": "stm",
            "service_id": "holiday",
            "start_date": date(2026, 10, 12),
            "end_date": date(2026, 10, 12),
        },
    ]
    exceptions = [
        dict(
            feed_id="stm",
            service_id="weekday",
            date=date(2026, 10, 12),
            exception_type=2,
        )
    ]
    database(monkeypatch, calendars=calendars, exceptions=exceptions)
    assert read_active_services("stm", date(2026, 10, 12)) == ("holiday",)


def test_database_result_is_sorted_and_isolated_from_other_feeds(monkeypatch):
    calendars = [
        regular() | {"service_id": "z"},
        regular() | {"feed_id": "stm", "service_id": "other"},
        regular() | {"service_id": "a"},
    ]
    exceptions = [
        dict(feed_id="stm", service_id="a", date=date(2026, 10, 5), exception_type=2)
    ]
    conn, _ = database(monkeypatch, calendars=calendars, exceptions=exceptions)
    assert read_active_services(" rem ", date(2026, 10, 5)) == ("a", "z")
    assert all(call.args[1] == ("rem",) for call in conn.execute.call_args_list[1:])


@pytest.mark.parametrize(
    "day,expected",
    [(date(2026, 6, 15), ("weekday",)), (date(2026, 10, 25), ())],
)
def test_feed_coverage_endpoints_are_accepted(monkeypatch, day, expected):
    database(monkeypatch, calendars=[regular()])
    assert read_active_services("rem", day) == expected


@pytest.mark.parametrize(
    "coverage",
    [
        (None, date(2026, 10, 25)),
        (date(2026, 6, 15), None),
        ("2026-06-15", date(2026, 10, 25)),
        (date(2026, 10, 25), date(2026, 6, 15)),
    ],
)
def test_invalid_database_coverage_stops_before_reading_calendars(
    monkeypatch, coverage
):
    conn, _ = database(monkeypatch, coverage=coverage)
    with pytest.raises(ValueError, match="feed_start_date/feed_end_date"):
        read_active_services("rem", date(2026, 10, 5))
    assert conn.execute.call_count == 2


@pytest.mark.parametrize("field,value", [("service_id", None), ("monday", None)])
def test_null_required_database_values_are_rejected(monkeypatch, field, value):
    database(monkeypatch, calendars=[regular() | {field: value}])
    with pytest.raises(ValueError, match=f"calendar row 2: {field}"):
        read_active_services("rem", date(2026, 10, 5))


def test_query_failure_is_sanitized_and_closes_connection(monkeypatch, capsys):
    conn, _ = database(monkeypatch)
    conn.execute.side_effect = psycopg.OperationalError("private database details")
    assert main(["--feed", "rem", "--date", "2026-10-05"]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "Could not read Supabase" in captured.err
    assert "private database details" not in captured.err
    assert conn.__exit__.called


def test_queries_bind_feed_instead_of_interpolating(monkeypatch):
    conn, _ = database(monkeypatch)
    feed = "x'; DROP TABLE gtfs.feeds; --"
    assert read_active_services(feed, date(2026, 10, 5)) == ()
    for call in conn.execute.call_args_list[1:]:
        assert feed not in call.args[0]
        assert call.args[1] == (feed,)
        assert "WHERE feed_id = %s" in call.args[0]


def test_unknown_feed_is_rejected(monkeypatch):
    database(monkeypatch, feed=False)
    with pytest.raises(ValueError, match="feed_id was not found"):
        read_active_services("rem", date(2026, 10, 5))


@pytest.mark.parametrize("day", [date(2026, 6, 14), date(2026, 10, 26)])
def test_dates_outside_feed_coverage_are_rejected(monkeypatch, day):
    conn, _ = database(monkeypatch)
    with pytest.raises(ValueError, match="coverage"):
        read_active_services("rem", day)
    assert conn.execute.call_count == 2


def test_missing_credentials_have_clear_error(monkeypatch):
    monkeypatch.delenv("SUPABASE_DB_URL", raising=False)
    with pytest.raises(ValueError, match="SUPABASE_DB_URL"):
        read_active_services("rem", date(2026, 10, 5))


def test_cli_does_not_leak_connection_errors(monkeypatch, capsys):
    _, connect = database(monkeypatch)
    connect.side_effect = psycopg.OperationalError("password=secret internal host")
    assert main(["--feed", "rem", "--date", "2026-10-05"]) == 1
    captured = capsys.readouterr()
    assert "Could not read" in captured.err
    assert "secret" not in captured.err
    assert "Traceback" not in captured.err
    assert captured.out == ""


def test_cli_outputs_reproducible_json(monkeypatch, capsys):
    database(monkeypatch, calendars=[regular()])
    assert main(["--feed", "rem", "--date", "2026-10-05"]) == 0
    assert capsys.readouterr().out == (
        '{"feed_id": "rem", "service_date": "2026-10-05", "service_ids": ["weekday"]}\n'
    )


@pytest.fixture(autouse=True)
def local_env(monkeypatch, tmp_path):
    """Keep tests isolated from the project's real .env."""
    path = tmp_path / ".env"
    monkeypatch.setattr("scripts.supabase_calendar.PROJECT_ENV_FILE", path)
    return path


def test_cli_loads_local_url_without_expansion_or_other_variables(
    monkeypatch, local_env, capsys
):
    _, connect = database(monkeypatch, calendars=[regular()])
    monkeypatch.delenv("SUPABASE_DB_URL")
    monkeypatch.delenv("TRANSITSYNC_UNUSED_SETTING", raising=False)
    url = "postgresql://example.invalid/${UNCHANGED}"
    local_env.write_text(
        f'SUPABASE_DB_URL="{url}"\nSUPABASE_SSL_ROOT_CERT=/local/ca.crt\n'
        "TRANSITSYNC_UNUSED_SETTING=unused\n",
        encoding="utf-8",
    )
    assert main(["--feed", "rem", "--date", "2026-10-05"]) == 0
    assert connect.call_args.args == (url,)
    assert connect.call_args.kwargs["sslrootcert"] == "/local/ca.crt"
    assert "TRANSITSYNC_UNUSED_SETTING" not in os.environ
    captured = capsys.readouterr()
    assert '"weekday"' in captured.out
    assert url not in captured.out + captured.err


def test_cli_environment_url_takes_precedence(monkeypatch, local_env):
    _, connect = database(monkeypatch)
    local_env.write_text("SUPABASE_DB_URL=unused\n", encoding="utf-8")
    assert main(["--feed", "rem", "--date", "2026-10-05"]) == 0
    assert connect.call_args.args == ("postgresql://example.invalid/test",)


def test_cli_exported_url_uses_local_certificate(monkeypatch, local_env):
    _, connect = database(monkeypatch)
    local_env.write_text(
        "SUPABASE_DB_URL=unused\nSUPABASE_SSL_ROOT_CERT=/local/ca.crt\n",
        encoding="utf-8",
    )
    assert main(["--feed", "rem", "--date", "2026-10-05"]) == 0
    assert connect.call_args.args == ("postgresql://example.invalid/test",)
    assert connect.call_args.kwargs["sslrootcert"] == "/local/ca.crt"


def test_cli_exported_certificate_takes_precedence(monkeypatch, local_env):
    _, connect = database(monkeypatch)
    monkeypatch.delenv("SUPABASE_DB_URL")
    monkeypatch.setenv("SUPABASE_SSL_ROOT_CERT", "/exported/ca.crt")
    local_env.write_text(
        "SUPABASE_DB_URL=postgresql://example.invalid/local\n"
        "SUPABASE_SSL_ROOT_CERT=/local/ca.crt\n",
        encoding="utf-8",
    )
    assert main(["--feed", "rem", "--date", "2026-10-05"]) == 0
    assert connect.call_args.args == ("postgresql://example.invalid/local",)
    assert connect.call_args.kwargs["sslrootcert"] == "/exported/ca.crt"


def test_cli_complete_environment_skips_invalid_local_file(monkeypatch, local_env):
    _, connect = database(monkeypatch)
    monkeypatch.setenv("SUPABASE_SSL_ROOT_CERT", "/exported/ca.crt")
    local_env.write_bytes(b"\xffinvalid")
    assert main(["--feed", "rem", "--date", "2026-10-05"]) == 0
    assert connect.call_args.args == ("postgresql://example.invalid/test",)
    assert connect.call_args.kwargs["sslrootcert"] == "/exported/ca.crt"


def test_cli_missing_local_url_is_actionable(monkeypatch, local_env, capsys):
    _, connect = database(monkeypatch)
    monkeypatch.delenv("SUPABASE_DB_URL")
    assert main(["--feed", "rem", "--date", "2026-10-05"]) == 1
    assert "SUPABASE_DB_URL" in capsys.readouterr().err
    connect.assert_not_called()


def test_cli_invalid_env_encoding_does_not_expose_contents(
    monkeypatch, local_env, capsys
):
    _, connect = database(monkeypatch)
    monkeypatch.delenv("SUPABASE_DB_URL")
    local_env.write_bytes(b"SUPABASE_DB_URL=\xffprivate-value")
    assert main(["--feed", "rem", "--date", "2026-10-05"]) == 1
    captured = capsys.readouterr()
    assert "UTF-8" in captured.err
    assert "private-value" not in captured.err
    connect.assert_not_called()
