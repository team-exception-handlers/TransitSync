# AI contribution: 50% or more AI-generated
from datetime import date

import pytest

from scripts.gtfs_calendar import active_service_ids


@pytest.mark.parametrize(
    ("feed", "day", "expected"),
    [
        ("rem", "2026-10-05", ("weekday",)),
        ("rem", "2026-10-10", ("saturday",)),
        ("rem", "2026-10-11", ("sunday",)),
        ("rem", "2026-10-12", ("sunday",)),
        ("stm", "2026-10-05", ("weekday",)),
        ("stm", "2026-10-12", ("holiday",)),
    ],
)
def test_weekday_weekend_and_feed_specific_holiday(feed, day, expected):
    assert (
        active_service_ids(
            service_calendars(),
            service_exceptions(),
            feed_id=feed,
            service_date=date.fromisoformat(day),
        )
        == expected
    )


def calendar(**changes):
    row = dict(
        feed_id="a",
        service_id="regular",
        start_date="20261005",
        end_date="20261012",
        monday="1",
        tuesday="0",
        wednesday="0",
        thursday="0",
        friday="0",
        saturday="0",
        sunday="0",
    )
    return row | changes


def service_calendars():
    """Synthetic calendars with different REM and STM holiday rules."""
    weekdays = dict(tuesday="1", wednesday="1", thursday="1", friday="1")
    return [
        calendar(feed_id="rem", service_id="weekday", end_date="20261224", **weekdays),
        calendar(
            feed_id="rem",
            service_id="saturday",
            monday="0",
            saturday="1",
            end_date="20261231",
        ),
        calendar(
            feed_id="rem",
            service_id="sunday",
            monday="0",
            sunday="1",
            end_date="20261231",
        ),
        calendar(feed_id="stm", service_id="weekday", **weekdays),
        calendar(feed_id="stm", service_id="holiday", start_date="20261012"),
    ]


def service_exceptions():
    return [
        dict(feed_id="rem", service_id="weekday", date="20261012", exception_type="2"),
        dict(feed_id="rem", service_id="sunday", date="20261012", exception_type="1"),
        dict(feed_id="stm", service_id="weekday", date="20261012", exception_type="2"),
        dict(feed_id="rem", service_id="saturday", date="20261228", exception_type="1"),
    ]


def select(calendars, exceptions=(), day=date(2026, 10, 5)):
    return active_service_ids(calendars, exceptions, feed_id="a", service_date=day)


@pytest.mark.parametrize(
    "day,expected",
    [
        (date(2026, 10, 5), ("regular",)),
        (date(2026, 10, 12), ("regular",)),
        (date(2026, 10, 19), ()),
    ],
)
def test_date_bounds_are_inclusive(day, expected):
    assert select([calendar()], day=day) == expected


def test_exception_only_service_and_feed_isolation():
    changes = [
        dict(feed_id="a", service_id="extra", date="20261005", exception_type="1"),
        dict(feed_id="b", service_id="regular", date="20261005", exception_type="2"),
    ]
    assert select([calendar(), calendar(feed_id="b", service_id="other")], changes) == (
        "extra",
        "regular",
    )
    assert select([], changes) == ("extra",)


@pytest.mark.parametrize(
    "field,value",
    [
        ("monday", "2"),
        ("start_date", "bad"),
        ("end_date", "20200101"),
        ("service_id", ""),
    ],
)
def test_invalid_calendar_fields_name_the_field(field, value):
    with pytest.raises(ValueError, match=field):
        select([calendar(**{field: value})])


def test_duplicate_exceptions_are_rejected():
    row = dict(feed_id="a", service_id="regular", date="20261005", exception_type="1")
    with pytest.raises(ValueError, match="duplicate"):
        select([calendar()], [row, row | {"exception_type": "2"}])


def test_invalid_exception_type_is_rejected():
    row = dict(feed_id="a", service_id="regular", date="20261005", exception_type="3")
    with pytest.raises(ValueError, match="exception_type"):
        select([], [row])


def test_duplicate_calendars_are_rejected():
    with pytest.raises(ValueError, match="duplicate"):
        select([calendar(), calendar()])


def test_missing_field_is_rejected():
    row = calendar()
    del row["monday"]
    with pytest.raises(ValueError, match="monday"):
        select([row])


def test_row_order_does_not_change_result():
    data = [calendar(service_id="z"), calendar(service_id="a")]
    assert select(data) == select(reversed(data)) == ("a", "z")


@pytest.mark.parametrize(
    "feed,day,field",
    [("", date(2026, 10, 5), "feed_id"), ("a", "2026-10-05", "service_date")],
)
def test_invalid_selection_arguments(feed, day, field):
    with pytest.raises(ValueError, match=field):
        active_service_ids([], [], feed_id=feed, service_date=day)


def test_exception_can_add_service_after_regular_calendar_ends():
    # The exception adds Saturday service after the weekday calendar ends.
    assert active_service_ids(
        service_calendars(),
        service_exceptions(),
        feed_id="rem",
        service_date=date(2026, 12, 28),
    ) == ("saturday",)
