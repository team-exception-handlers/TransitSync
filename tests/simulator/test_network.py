# AI contribution: 50% or more AI-generated
"""Static topology membership, completeness and ownership checks for #97."""

import logging
from dataclasses import FrozenInstanceError, replace
from types import MappingProxyType

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from simulator.network import build_network
from simulator.network_config import NetworkConfig
from simulator.timetable import Platform


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
