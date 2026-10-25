# AI contribution: 50% or more AI-generated
"""Static topology membership, completeness and ownership checks for #97."""

import json
import logging
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
from types import MappingProxyType

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from simulator.network import build_network
from simulator.network_config import NetworkConfig, load_network
from simulator.timetable import Platform, summarize_headways
from simulator.trains.train import ScheduledStop

REFERENCE_NETWORK = (
    Path(__file__).resolve().parents[2] / "config/reference_network/network.json"
)


@pytest.fixture(scope="module")
def saved_config() -> NetworkConfig:
    return load_network(REFERENCE_NETWORK)


def interchange(interchange_id="a", metro_line="green") -> tuple[Platform, ...]:
    return tuple(
        Platform(
            platform_id=f"{interchange_id}-{line}-{direction}",
            interchange_id=interchange_id,
            line_id=line,
            direction_id=direction,
            direction_label=f"Direction {direction}",
            stop_id=f"source-{interchange_id}-{line}",
            stop_name="Source station name",
            route_ids=("S1", "S2", "S3") if line == "rem" else ("route",),
        )
        for line in ("rem", metro_line)
        for direction in (0, 1)
    )


def config_for(platforms: tuple[Platform, ...]) -> NetworkConfig:
    return NetworkConfig(
        reference_dates=MappingProxyType({}),
        platforms=platforms,
        schedules=MappingProxyType({}),
        platform_feed_ids=MappingProxyType({}),
    )


def test_builds_complex_line_and_corridor_memberships_without_copying_platforms():
    config = config_for(interchange())
    network = build_network(config)

    assert tuple(network.platforms) == ("a-green-0", "a-green-1", "a-rem-0", "a-rem-1")
    for platform in config.platforms:
        assert network.platforms[platform.platform_id] is platform
    station = network.station_complexes["a"]
    assert station.interchange_id == "a"
    assert station.platform_ids == tuple(network.platforms)
    assert station.line_ids == ("green", "rem")
    assert network.lines["rem"].line_id == "rem"
    assert network.lines["rem"].platform_ids == ("a-rem-0", "a-rem-1")
    assert network.lines["green"].platform_ids == ("a-green-0", "a-green-1")
    corridor = network.corridors["a"]
    assert corridor.corridor_id == corridor.interchange_id == "a"
    assert corridor.rem_platform_ids == ("a-rem-0", "a-rem-1")
    assert corridor.metro_platform_ids == ("a-green-0", "a-green-1")
    assert config == config_for(interchange())


def test_global_line_membership_spans_complexes_and_preserves_saved_mapping():
    network = build_network(config_for(interchange("b", "blue") + interchange()))

    assert tuple(network.station_complexes) == ("a", "b")
    assert tuple(network.lines) == ("blue", "green", "rem")
    assert network.lines["rem"].platform_ids == (
        "a-rem-0",
        "a-rem-1",
        "b-rem-0",
        "b-rem-1",
    )
    assert network.station_complexes["b"].line_ids == ("blue", "rem")
    assert tuple(network.corridors) == ("a", "b")
    assert network.corridors["a"] is not network.corridors["b"]


@settings(max_examples=20)
@given(platforms=st.permutations(interchange() + interchange("b", "blue")))
def test_input_order_cannot_change_topology_or_iteration_order(platforms):
    expected = build_network(config_for(interchange() + interchange("b", "blue")))
    actual = build_network(config_for(tuple(platforms)))

    assert actual == expected
    for field in ("platforms", "station_complexes", "lines", "corridors"):
        assert tuple(getattr(actual, field).items()) == tuple(
            getattr(expected, field).items()
        )


@pytest.mark.parametrize(
    "field", ["platforms", "station_complexes", "lines", "corridors"]
)
def test_builder_returns_read_only_indexes(field):
    network = build_network(config_for(interchange()))
    index = getattr(network, field)
    key = next(iter(index))

    with pytest.raises(TypeError):
        index[key] = index[key]
    with pytest.raises(FrozenInstanceError):
        setattr(network, field, {})


@pytest.mark.parametrize(
    "field,identity,attribute,value",
    [
        ("platforms", "a-rem-0", "line_id", "other"),
        ("station_complexes", "a", "platform_ids", ()),
        ("lines", "rem", "platform_ids", ()),
        ("corridors", "a", "rem_platform_ids", ()),
    ],
)
def test_membership_records_are_immutable(field, identity, attribute, value):
    record = getattr(build_network(config_for(interchange())), field)[identity]
    with pytest.raises(FrozenInstanceError):
        setattr(record, attribute, value)


def test_empty_topology_is_rejected():
    with pytest.raises(ValueError, match="platforms.*empty"):
        build_network(config_for(()))


def test_duplicate_platform_id_is_rejected_before_it_can_overwrite_a_record():
    platforms = interchange()
    duplicate = replace(platforms[0], interchange_id="b")
    with pytest.raises(ValueError, match="a-rem-0.*duplicate"):
        build_network(config_for(platforms + (duplicate,)))


def test_duplicate_directional_membership_names_complex_line_and_platform():
    platforms = interchange()
    duplicate = replace(platforms[0], platform_id="duplicate")
    with pytest.raises(ValueError, match="a.*rem.*duplicate.*direction 0"):
        build_network(config_for(platforms + (duplicate,)))


@pytest.mark.parametrize("missing_index", range(4))
def test_incomplete_directional_group_is_rejected(missing_index):
    platforms = interchange()
    missing = platforms[missing_index]
    incomplete = tuple(p for p in platforms if p is not missing)
    with pytest.raises(ValueError, match=rf"a.*{missing.line_id}.*directions 0 and 1"):
        build_network(config_for(incomplete))


@pytest.mark.parametrize("remaining_line", ["rem", "green"])
def test_missing_corridor_side_is_rejected(remaining_line):
    platforms = tuple(p for p in interchange() if p.line_id == remaining_line)
    with pytest.raises(ValueError, match="a.*one REM.*one Métro"):
        build_network(config_for(platforms))


@pytest.mark.parametrize("misspelled_id", ["REM", "remm"])
def test_misspelled_rem_line_id_reports_expected_and_found_ids(misspelled_id):
    platforms = tuple(
        replace(p, line_id=misspelled_id) if p.line_id == "rem" else p
        for p in interchange()
    )
    with pytest.raises(ValueError) as exc_info:
        build_network(config_for(platforms))

    assert str(exc_info.value) == (
        "complex a: expected one REM and one Métro line group "
        f"with REM line ID 'rem'; found {sorted(['green', misspelled_id])}"
    )


def test_extra_line_group_cannot_be_silently_dropped():
    extra = tuple(p for p in interchange(metro_line="blue") if p.line_id == "blue")
    with pytest.raises(ValueError, match="a.*one REM.*one Métro"):
        build_network(config_for(interchange() + extra))


def test_two_metro_lines_cannot_form_a_rem_metro_corridor():
    platforms = tuple(
        p
        for line in ("green", "blue")
        for p in interchange(metro_line=line)
        if p.line_id != "rem"
    )
    with pytest.raises(ValueError, match="a.*one REM.*one Métro"):
        build_network(config_for(platforms))


def test_invalid_complex_prevents_returning_a_partial_network():
    with pytest.raises(ValueError, match="b.*rem.*directions 0 and 1"):
        build_network(config_for(interchange() + interchange("b", "blue")[1:]))


def test_construction_logs_one_completion_summary_and_no_success_on_failure(caplog):
    with caplog.at_level(logging.INFO, logger="simulator.network"):
        build_network(config_for(interchange()))
        with pytest.raises(ValueError):
            build_network(config_for(interchange()[1:]))

    assert len(caplog.records) == 1
    assert caplog.records[0].getMessage() == (
        "Built network: 1 station complexes, 2 lines, 4 platforms, 1 corridors"
    )


@pytest.mark.parametrize("complex_id,metro_line", [("a", "green"), ("b", "blue")])
@pytest.mark.parametrize("rem_direction", [0, 1])
@pytest.mark.parametrize("metro_direction", [0, 1])
@pytest.mark.parametrize("reverse", [False, True])
def test_transfer_pairs_share_one_corridor_in_both_directions(
    complex_id, metro_line, rem_direction, metro_direction, reverse
):
    network = build_network(config_for(interchange() + interchange("b", "blue")))
    endpoints = (
        f"{complex_id}-rem-{rem_direction}",
        f"{complex_id}-{metro_line}-{metro_direction}",
    )
    origin, destination = reversed(endpoints) if reverse else endpoints

    assert network.corridor_for(origin, destination) is network.corridors[complex_id]


@pytest.mark.parametrize(
    "origin,destination",
    [
        ("a-rem-0", "a-rem-0"),
        ("a-rem-0", "a-rem-1"),
        ("a-green-0", "a-green-1"),
        ("a-rem-0", "b-blue-0"),
        ("b-blue-0", "a-rem-0"),
        ("a-rem-0", "b-rem-0"),
        ("a-green-0", "b-blue-0"),
    ],
)
def test_known_platforms_without_a_transfer_link_return_none(origin, destination):
    network = build_network(config_for(interchange() + interchange("b", "blue")))

    assert network.corridor_for(origin, destination) is None


@pytest.mark.parametrize(
    "origin,destination,role,unknown_id",
    [
        ("missing-origin", "a-green-0", "origin", "missing-origin"),
        ("a-rem-0", "missing-destination", "destination", "missing-destination"),
        ("missing-origin", "missing-destination", "origin", "missing-origin"),
        ("a-green-0", "", "destination", ""),
    ],
)
def test_unknown_transfer_endpoint_raises_contextual_key_error(
    origin, destination, role, unknown_id
):
    network = build_network(config_for(interchange()))

    with pytest.raises(KeyError) as error:
        network.corridor_for(origin, destination)
    assert error.value.args[0].startswith(f"{role} platform ")
    assert repr(unknown_id) in str(error.value)


def test_transfer_lookup_uses_saved_membership_instead_of_parsing_platform_ids():
    platforms = tuple(
        replace(platform, platform_id=identity)
        for platform, identity in zip(
            interchange("custom-complex", "blue"),
            ("green-looking", "17", "rem-looking", "platform with spaces"),
            strict=True,
        )
    )
    network = build_network(config_for(platforms))
    corridor = network.corridors["custom-complex"]

    assert network.corridor_for("green-looking", "rem-looking") is corridor
    assert network.corridor_for("rem-looking", "17") is corridor
    assert network.corridor_for("green-looking", "17") is None


def test_transfer_queries_leave_topology_and_input_unchanged():
    config = config_for(interchange() + interchange("b", "blue"))
    network = build_network(config)
    before = repr(network)
    for origin in network.platforms:
        for destination in network.platforms:
            network.corridor_for(origin, destination)
    with pytest.raises(KeyError):
        network.corridor_for("unknown", "a-rem-0")

    assert repr(network) == before
    assert config == config_for(interchange() + interchange("b", "blue"))


def test_saved_config_builds_the_full_network_with_reused_platforms(saved_config):
    network = build_network(saved_config)

    assert set(network.station_complexes) == {
        "gare_centrale_bonaventure",
        "mcgill",
        "edouard_montpetit",
    }
    assert set(network.lines) == {"rem", "orange", "green", "blue"}
    assert len(network.platforms) == 12
    assert set(network.corridors) == set(network.station_complexes)
    assert network.lines["rem"].platform_ids == (
        "rem_edouard_montpetit_0",
        "rem_edouard_montpetit_1",
        "rem_gare_centrale_bonaventure_0",
        "rem_gare_centrale_bonaventure_1",
        "rem_mcgill_0",
        "rem_mcgill_1",
    )
    for platform in saved_config.platforms:
        assert network.platforms[platform.platform_id] is platform


@pytest.mark.parametrize(
    "complex_id,metro_line",
    [
        ("gare_centrale_bonaventure", "orange"),
        ("mcgill", "green"),
        ("edouard_montpetit", "blue"),
    ],
)
def test_saved_complex_memberships_and_all_transfer_endpoints(
    saved_config, complex_id, metro_line
):
    network = build_network(saved_config)
    rem_ids = (f"rem_{complex_id}_0", f"rem_{complex_id}_1")
    metro_ids = (f"{metro_line}_{complex_id}_0", f"{metro_line}_{complex_id}_1")
    station = network.station_complexes[complex_id]
    corridor = network.corridors[complex_id]

    assert station.interchange_id == complex_id
    assert station.platform_ids == tuple(sorted(rem_ids + metro_ids))
    assert station.line_ids == tuple(sorted(("rem", metro_line)))
    assert network.lines[metro_line].platform_ids == metro_ids
    assert corridor.corridor_id == corridor.interchange_id == complex_id
    assert corridor.rem_platform_ids == rem_ids
    assert corridor.metro_platform_ids == metro_ids
    for rem_id in rem_ids:
        for metro_id in metro_ids:
            assert network.corridor_for(rem_id, metro_id) is corridor
            assert network.corridor_for(metro_id, rem_id) is corridor
    assert network.corridor_for(*rem_ids) is None
    assert network.corridor_for(*metro_ids) is None


def test_saved_visit_ids_resolve_to_runtime_stop_identities(saved_config):
    network = build_network(saved_config)
    seen_platforms = set()
    for trips in saved_config.schedules.values():
        for trip in trips:
            for visit in trip.visits:
                platform = network.platforms[visit.platform_id]
                # Synthetic relative times: schedule conversion belongs to assembly.
                stop = ScheduledStop(
                    station_id=platform.interchange_id,
                    platform_id=visit.platform_id,
                    arrival_s=0,
                    departure_s=30,
                )
                station = network.station_complexes[stop.station_id]
                assert stop.platform_id in station.platform_ids
                assert stop.platform_id in network.lines[platform.line_id].platform_ids
                assert platform.stop_id == visit.stop_id
                seen_platforms.add(stop.platform_id)
    assert seen_platforms == set(network.platforms)


def test_saved_config_empty_service_preserves_full_topology(tmp_path, saved_config):
    raw = json.loads(REFERENCE_NETWORK.read_text(encoding="utf-8"))
    for day in raw["schedules"]:
        day["trips"] = []
        day["headways"] = summarize_headways(saved_config.platforms, ())
    path = tmp_path / "empty-service.json"
    path.write_text(json.dumps(raw), encoding="utf-8")

    empty_service = load_network(path)

    assert all(trips == () for trips in empty_service.schedules.values())
    assert build_network(empty_service) == build_network(saved_config)


def test_reader_valid_split_group_fails_topology_construction(tmp_path):
    raw = json.loads(REFERENCE_NETWORK.read_text(encoding="utf-8"))
    for day in raw["schedules"]:
        for platform in day["platforms"]:
            if platform["platform_id"] == "rem_mcgill_1":
                # Sort after McGill so its missing direction is reported first.
                platform["interchange_id"] = "zz_incomplete"
    path = tmp_path / "split-group.json"
    path.write_text(json.dumps(raw), encoding="utf-8")

    config = load_network(path)

    split_platform = next(
        p for p in config.platforms if p.platform_id == "rem_mcgill_1"
    )
    assert split_platform.interchange_id == "zz_incomplete"
    with pytest.raises(
        ValueError, match="complex mcgill, line rem:.*directions 0 and 1"
    ):
        build_network(config)
