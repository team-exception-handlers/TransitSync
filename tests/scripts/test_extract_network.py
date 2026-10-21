# AI contribution: 50% or more AI-generated
"""Config generation, report stability and safe publication."""

import copy
from pathlib import Path

import pytest

from scripts.extract_network import build_config, write_config
from tests.simulator.test_network_config import config as config


def test_build_and_publish_then_load_without_database(tmp_path, config):
    from simulator.network_config import load_network

    previews = []
    for day in config["schedules"]:
        preview = copy.deepcopy(day)
        preview.pop("headways")
        preview["preview_schema_version"] = 1
        previews.append(preview)
    built = build_config(previews, config["reference_dates"], config["map_evidence"])
    assert "$comment" not in built
    folder = tmp_path / "network"
    write_config(built, folder)
    assert (
        load_network(folder / "network.json").reference_dates["weekday"].isoformat()
        == "2026-10-05"
    )
    report = (folder / "report.md").read_text()
    assert "2026-10-05" in report and "Boarding-eligible" in report
    assert "representative" in report.lower()
    before = {p.name: p.read_bytes() for p in folder.iterdir()}
    write_config(built, folder)
    assert before == {p.name: p.read_bytes() for p in folder.iterdir()}


def test_invalid_or_changed_output_cannot_replace_previous_config(tmp_path, config):
    folder = tmp_path / "network"
    write_config(config, folder)
    original = (folder / "network.json").read_bytes()
    changed = copy.deepcopy(config)
    changed["schema_version"] = 99
    with pytest.raises(ValueError):
        write_config(changed, folder)
    changed = copy.deepcopy(config)
    changed["map_evidence"][0]["notes"] = "Changed valid evidence"
    with pytest.raises(ValueError, match="already exists"):
        write_config(changed, folder)
    assert (folder / "network.json").read_bytes() == original


def test_write_failure_does_not_publish_partial_bundle(tmp_path, config, monkeypatch):
    original = Path.write_text

    def write(path, *args, **kwargs):
        if path.name == "report.md":
            raise OSError("simulated disk failure")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", write)
    with pytest.raises(OSError):
        write_config(config, tmp_path / "network")
    assert not (tmp_path / "network").exists()
    assert list(tmp_path.iterdir()) == []


def test_cli_builds_real_reader_output_with_mocked_connection(
    tmp_path, monkeypatch, capsys
):
    from scripts import extract_network as cli
    from tests.scripts.test_supabase_schedule import PLATFORM, connect_database

    connect_database(monkeypatch)
    monkeypatch.setattr(cli, "load_mapping", lambda path: {"rem": (PLATFORM,)})
    monkeypatch.setattr(cli, "_load_local_connection_settings", lambda: None)
    output = tmp_path / "result"
    assert cli.main(["--output-dir", str(output)]) == 0
    assert (output / "network.json").exists()
    assert "Saved three reference schedules" in capsys.readouterr().out


@pytest.mark.parametrize("existing", [False, True])
def test_no_active_services_prevent_publication(
    tmp_path, monkeypatch, caplog, config, existing
):
    from scripts import extract_network as cli
    from tests.scripts.test_supabase_schedule import PLATFORM, connect_database

    _, _, rows = connect_database(monkeypatch)
    rows["gtfs.calendar"] = []
    monkeypatch.setattr(cli, "load_mapping", lambda path: {"rem": (PLATFORM,)})
    monkeypatch.setattr(cli, "_load_local_connection_settings", lambda: None)
    output = tmp_path / "result"
    if existing:
        write_config(config, output)
    before = {p.name: p.read_bytes() for p in output.iterdir()} if existing else {}
    assert cli.main(["--output-dir", str(output)]) == 1
    assert "feed 'rem'" in caplog.text
    assert "2026-10-05" in caplog.text and "no active services" in caplog.text
    if existing:
        assert before == {p.name: p.read_bytes() for p in output.iterdir()}
    else:
        assert not output.exists()


def test_report_is_stable_after_json_round_trip(config):
    import json

    from scripts.extract_network import render_report

    assert render_report(config) == render_report(
        json.loads(json.dumps(config, sort_keys=True))
    )
