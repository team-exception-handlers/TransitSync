# AI contribution: 50% or more AI-generated
"""Select active GTFS services for a date (#88)."""

from collections.abc import Iterable, Mapping
from datetime import date

WEEKDAYS = (
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
)
type Row = Mapping[str, str]


def _text(row: Row, field: str) -> str:
    value = row.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be non-empty text")
    return value.strip()


def _date(row: Row, field: str) -> date:
    value = _text(row, field)
    if len(value) == 8 and value.isascii() and value.isdigit():
        value = f"{value[:4]}-{value[4:6]}-{value[6:]}"
    try:
        if len(value) != 10 or value[4] != "-" or value[7] != "-":
            raise ValueError
        return date.fromisoformat(value)
    except ValueError as error:
        raise ValueError(
            f"{field} must be a valid YYYY-MM-DD or YYYYMMDD date"
        ) from error


def _service_window(row: Row) -> tuple[date, date, list[str]]:
    """Validate a calendar row's date range and weekday flags."""
    start, end = _date(row, "start_date"), _date(row, "end_date")
    if end < start:
        raise ValueError("end_date must be on or after start_date")
    flags = [_text(row, weekday) for weekday in WEEKDAYS]
    for weekday, flag in zip(WEEKDAYS, flags, strict=True):
        if flag not in ("0", "1"):
            raise ValueError(f"{weekday} must be 0 or 1")
    return start, end, flags


def _regular_services(rows: Iterable[Row], feed_id: str, day: date) -> set[str]:
    active: set[str] = set()
    seen: set[str] = set()
    for number, row in enumerate(rows, start=2):
        try:
            if _text(row, "feed_id") != feed_id:
                continue
            service = _text(row, "service_id")
            if service in seen:
                raise ValueError(f"duplicate service_id {service!r}")
            seen.add(service)
            start, end, flags = _service_window(row)
            if start <= day <= end and flags[day.weekday()] == "1":
                active.add(service)
        except ValueError as error:
            raise ValueError(f"calendar row {number}: {error}") from error
    return active


def _apply_exceptions(
    rows: Iterable[Row], feed_id: str, day: date, active: set[str]
) -> None:
    seen: set[tuple[str, date]] = set()
    for number, row in enumerate(rows, start=2):
        try:
            if _text(row, "feed_id") != feed_id:
                continue
            service = _text(row, "service_id")
            exception_day = _date(row, "date")
            kind = _text(row, "exception_type")
            if kind not in ("1", "2"):
                raise ValueError("exception_type must be 1 (add) or 2 (remove)")
            key = (service, exception_day)
            if key in seen:
                raise ValueError(f"duplicate service_id/date {key!r}")
            seen.add(key)
            if exception_day != day:
                continue
            if kind == "1":
                active.add(service)
            else:
                active.discard(service)
        except ValueError as error:
            raise ValueError(f"calendar_dates row {number}: {error}") from error


def active_service_ids(
    calendar_rows: Iterable[Row],
    exception_rows: Iterable[Row],
    *,
    feed_id: str,
    service_date: date,
) -> tuple[str, ...]:
    """Return sorted active service IDs for one feed and date.

    Rows contain text values with YYYY-MM-DD or YYYYMMDD dates. Apply weekday
    flags and inclusive date ranges, then exceptions, including added services.
    Ignore other feeds; reject invalid selected-feed rows and duplicate keys.
    An empty result means no matching service; callers must check feed coverage.
    Service dates are not shifted for overnight trips.
    """
    if not isinstance(feed_id, str) or not feed_id.strip():
        raise ValueError("feed_id must be non-empty text")
    if type(service_date) is not date:
        raise ValueError("service_date must be a datetime.date, without a time")
    feed_id = feed_id.strip()
    active = _regular_services(calendar_rows, feed_id, service_date)
    _apply_exceptions(exception_rows, feed_id, service_date, active)
    return tuple(sorted(active))
