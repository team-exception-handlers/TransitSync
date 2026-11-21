# AI contribution: 50% or more AI-generated
"""Passenger outcomes retain missed services, later boarding and unfinished walks."""

from fastapi.testclient import TestClient

from api.main import create_app
from api.passenger_outcomes import build_passenger_outcomes
from api.station_layout import Connection


def test_outcomes_use_event_order_and_keep_unfinished_transfers():
    connection = Connection(
        id="link",
        label="Transfer",
        from_platform_id="rem",
        to_platform_id="metro",
        corridor_id="corridor",
    )

    def event(kind, time, platform="metro", **fields):
        return dict(event_type=kind, time_s=time, platform_id=platform, **fields)

    events = [
        event("alighting", 0, "rem", passenger_id="late"),
        event("train_departure", 3, "other", train_id="unrelated"),
        event("train_departure", 5, train_id="first"),
        event("passenger_arrival", 6, passenger_id="late"),
        event("train_departure", 10, train_id="second"),
        event("alighting", 11, "rem", passenger_id="ontime"),
        event("passenger_arrival", 15, passenger_id="ontime"),
        event("boarding", 15, passenger_id="ontime", train_id="third"),
        event("boarding", 15, passenger_id="late", train_id="third"),
        event("train_departure", 15, train_id="third"),
        event("alighting", 16, "rem", passenger_id="walking"),
        event("alighting", 17, "rem", passenger_id="held"),
        event("passenger_arrival", 18, passenger_id="held"),
        event("boarding", 19, passenger_id="held", train_id="fourth"),
    ]
    held, late, ontime, walking = build_passenger_outcomes(events, connection)
    assert held.status == "made"
    assert held.boarding_s == 19
    assert held.departure_s is None
    assert late.status == "missed"
    assert late.missed_train_ids == ["first", "second"]
    assert late.platform_arrival_s == 6
    assert late.boarded_train_id == "third"
    assert late.departure_s == 15
    assert late.transfer_time_s == 15
    assert late.delay_s == 10
    assert ontime.status == "made"
    assert ontime.delay_s == 0
    assert ontime.missed_train_ids == []
    assert walking.status == "pending"
    assert walking.platform_arrival_s is walking.departure_s is walking.delay_s is None


def test_comparison_matches_each_cached_run():
    client = TestClient(create_app())
    settings = dict(connection_id="mcgill-rem-green", strategy="connection_protection")
    response = client.post("/simulation/passenger-comparison", json=settings)
    assert response.status_code == 200
    comparison = response.json()
    for key, strategy in [
        ("without_holding", "no_control"),
        ("selected_strategy", "connection_protection"),
    ]:
        run = client.post(
            "/simulation/run", json={**settings, "strategy": strategy}
        ).json()
        assert comparison[key] == run["passenger_outcomes"]
        assert comparison[key]
        assert [o["passenger_id"] for o in comparison[key]] == [
            t["passenger_id"] for t in run["passenger_tracks"]
        ]
