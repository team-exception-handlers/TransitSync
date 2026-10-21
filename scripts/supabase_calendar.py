# AI contribution: 50% or more AI-generated
"""Read GTFS service calendars from Supabase during offline extraction."""

import argparse
import json
import logging
import os
from datetime import date
from pathlib import Path

import psycopg
from dotenv import dotenv_values

from scripts.extraction_logging import configure_logging
from scripts.gtfs_calendar import active_service_ids
from scripts.supabase_connection import read_only_connection

logger = logging.getLogger(__name__)

PROJECT_ENV_FILE = Path(__file__).resolve().parents[1] / ".env"

FEED_QUERY = """
SELECT feed_start_date, feed_end_date FROM gtfs.feeds WHERE feed_id = %s
"""
CALENDAR_QUERY = """
SELECT feed_id, service_id, monday, tuesday, wednesday, thursday, friday,
       saturday, sunday, start_date, end_date
FROM gtfs.calendar WHERE feed_id = %s ORDER BY service_id
"""
EXCEPTIONS_QUERY = """
SELECT feed_id, service_id, date, exception_type
FROM gtfs.calendar_dates WHERE feed_id = %s ORDER BY service_id, date
"""


class SupabaseReadError(RuntimeError):
    """A connection or query error without private database details."""


def _load_local_connection_settings() -> None:
    """Load missing connection settings from the project-root .env."""
    keys = ("SUPABASE_DB_URL", "SUPABASE_SSL_ROOT_CERT")
    if all(key in os.environ for key in keys):
        return
    try:
        settings = dotenv_values(PROJECT_ENV_FILE, interpolate=False, encoding="utf-8")
    except (OSError, UnicodeError):
        raise SupabaseReadError(
            "Could not read project .env. Check file permissions and UTF-8 encoding."
        ) from None
    for key in keys:
        value = settings.get(key)
        if key not in os.environ and value is not None:
            os.environ[key] = value


def _text_rows(rows: list[dict]) -> list[dict[str, str]]:
    """Convert database values to text; keep NULL empty for validation."""
    return [
        {key: "" if value is None else str(value) for key, value in row.items()}
        for row in rows
    ]


def _read_calendar(connection, feed_id: str, service_date: date) -> tuple[str, ...]:
    """Check feed coverage and select services within the current transaction."""
    connection.execute("SET LOCAL statement_timeout = '15s'")
    feed = connection.execute(FEED_QUERY, (feed_id,)).fetchone()
    if feed is None:
        raise ValueError("feed_id was not found in gtfs.feeds")
    start, end = feed["feed_start_date"], feed["feed_end_date"]
    if type(start) is not date or type(end) is not date or end < start:
        raise ValueError("feed_start_date/feed_end_date must define valid coverage")
    if not start <= service_date <= end:
        raise ValueError(f"service_date is outside feed coverage ({start} to {end})")
    calendars = connection.execute(CALENDAR_QUERY, (feed_id,)).fetchall()
    exceptions = connection.execute(EXCEPTIONS_QUERY, (feed_id,)).fetchall()
    return active_service_ids(
        _text_rows(calendars),
        _text_rows(exceptions),
        feed_id=feed_id,
        service_date=service_date,
    )


def read_active_services(feed_id: str, service_date: date) -> tuple[str, ...]:
    """Read active service IDs from one read-only database snapshot.

    Read credentials from the process environment; only the CLI loads .env.
    Requires SELECT on gtfs.feeds, gtfs.calendar, and gtfs.calendar_dates.
    Database failures raise SupabaseReadError without raw diagnostics.
    """
    if not isinstance(feed_id, str) or not feed_id.strip():
        raise ValueError("feed_id must be non-empty text")
    if type(service_date) is not date:
        raise ValueError("service_date must be a datetime.date, without a time")
    logger.info("Reading calendar: feed=%r service_date=%s", feed_id, service_date)
    try:
        with read_only_connection() as connection:
            services = _read_calendar(connection, feed_id.strip(), service_date)
    except psycopg.Error:
        logger.error(
            "Calendar read failed: feed=%r service_date=%s", feed_id, service_date
        )
        raise SupabaseReadError(
            "Could not read Supabase GTFS data. Check connection settings, "
            "network access, TLS certificates, and SELECT permissions."
        ) from None
    logger.info(
        "Calendar read completed: feed=%r service_date=%s services=%d",
        feed_id,
        service_date,
        len(services),
    )
    return services


def main(argv: list[str] | None = None) -> int:
    """Print service IDs as JSON or a safe error to stderr."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--feed", required=True, help="Exact gtfs.feeds feed_id")
    parser.add_argument("--date", required=True, type=date.fromisoformat)
    args = parser.parse_args(argv)
    configure_logging()
    try:
        _load_local_connection_settings()
        services = read_active_services(args.feed, args.date)
    except (ValueError, SupabaseReadError) as error:
        logger.error(
            "Calendar command failed: feed=%r service_date=%s: %s",
            args.feed,
            args.date,
            error,
        )
        return 1
    print(
        json.dumps(
            {
                "feed_id": args.feed.strip(),
                "service_date": args.date.isoformat(),
                "service_ids": services,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
