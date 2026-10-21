# AI contribution: 50% or more AI-generated
"""Extraction logs provide context without exposing connection diagnostics."""

import json
import logging
import subprocess
import sys

import psycopg
import pytest

from scripts import extract_network, supabase_calendar, supabase_schedule
from tests.scripts.test_supabase_calendar import database
from tests.scripts.test_supabase_schedule import DAY, PLATFORM, connect_database


@pytest.mark.parametrize("kind", ["calendar", "schedule"])
def test_success_logs_context_and_keeps_stdout_json(kind, monkeypatch, caplog, capsys):
    caplog.set_level(logging.INFO)
    if kind == "calendar":
        database(monkeypatch)
        cli = supabase_calendar
        arguments = ["--feed", "rem", "--date", DAY.isoformat()]
    else:
        connect_database(monkeypatch)
        cli = supabase_schedule
        monkeypatch.setattr(cli, "load_mapping", lambda path: {"rem": (PLATFORM,)})
        arguments = ["--date", DAY.isoformat()]
    monkeypatch.setattr(cli, "_load_local_connection_settings", lambda: None)
    assert cli.main(arguments) == 0
    assert json.loads(capsys.readouterr().out)["service_date"] == DAY.isoformat()
    assert "rem" in caplog.text and DAY.isoformat() in caplog.text
    assert any("completed" in record.message for record in caplog.records)


@pytest.mark.parametrize("kind", ["calendar", "schedule-connect", "schedule-query"])
def test_database_failure_logs_context_without_secrets(kind, monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    if kind == "calendar":
        _, connect = database(monkeypatch)
    else:
        connection, connect, _ = connect_database(monkeypatch)
        # Fail during a feed read, after the connection has been established.
        connection.execute.side_effect = psycopg.OperationalError("private-diagnostic")
    if kind != "schedule-query":
        connect.side_effect = psycopg.OperationalError("private-diagnostic")
    monkeypatch.setenv("SUPABASE_DB_URL", "postgresql://user:private-password@host/db")
    with pytest.raises(supabase_calendar.SupabaseReadError):
        if kind == "calendar":
            supabase_calendar.read_active_services("rem", DAY)
        else:
            supabase_schedule.read_daily_schedule({"rem": (PLATFORM,)}, DAY)
    errors = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert any("rem" in r.message and DAY.isoformat() in r.message for r in errors)
    assert "private-password" not in caplog.text
    assert "private-diagnostic" not in caplog.text
    assert all(r.exc_info is None for r in errors)


def test_publication_failure_is_logged_without_raw_disk_error(monkeypatch, caplog):
    monkeypatch.setattr(
        extract_network, "_load_local_connection_settings", lambda: None
    )
    monkeypatch.setattr(extract_network, "load_mapping", lambda path: {})
    monkeypatch.setattr(extract_network, "read_schedules", lambda *args: [])
    monkeypatch.setattr(extract_network, "build_config", lambda *args: {})

    def fail(*args):
        raise OSError("private-disk-details")

    monkeypatch.setattr(extract_network, "write_config", fail)
    assert extract_network.main([]) == 1
    assert "Could not save configuration" in caplog.text
    assert "private-disk-details" not in caplog.text


def test_cli_routes_progress_and_errors_to_stderr():
    result = subprocess.run(
        [sys.executable, "-m", "scripts.extract_network", "--weekday", "2026-10-10"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert result.stdout == ""
    assert "INFO" in result.stderr and "Starting reference extraction" in result.stderr
    assert "ERROR" in result.stderr and "reference dates must match" in result.stderr
    assert "Traceback" not in result.stderr
