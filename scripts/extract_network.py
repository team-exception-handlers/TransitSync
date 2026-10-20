# AI contribution: 50% or more AI-generated
"""Generate reference schedule JSON and its report (#88)."""

import argparse
import json
import logging
import tempfile
from datetime import date
from pathlib import Path

from scripts.extraction_logging import configure_logging
from scripts.supabase_calendar import SupabaseReadError, _load_local_connection_settings
from scripts.supabase_schedule import DEFAULT_MAPPING, load_mapping, read_schedules
from simulator.network_config import load_network, parse_timetable, validate_network
from simulator.timetable import summarize_headways

logger = logging.getLogger(__name__)

DEFAULT_OUTPUT = Path(__file__).resolve().parents[1] / "config/reference_network"
MAP_EVIDENCE = [
    {
        "url": "https://www.stm.info/sites/default/files/media/Stminfo/images/planmetropolitain.pdf",
        "checked_on": "2026-10-19",
        "notes": "Visually checked: Gare Centrale/Bonaventure orange; McGill green; "
        "Édouard-Montpetit blue. Métro endpoints and REM station order agree with "
        "source trips. Map date: 2026-02-06. Quay IDs come from GTFS.",
    },
    *[
        {
            "url": f"https://rem.info/en/travelling/stations/{station}",
            "checked_on": "2026-10-19",
            "notes": "Official station connection corroborates mapped Métro line",
        }
        for station in ("gare-centrale", "mcgill", "edouard-montpetit")
    ],
]


def build_config(
    previews: list[dict], reference_dates: dict, map_evidence: list
) -> dict:
    """Build config for three reference dates."""
    schedules = []
    attribution = set()
    for preview in sorted(previews, key=lambda p: p["service_date"]):
        day = {
            key: value
            for key, value in preview.items()
            if key != "preview_schema_version"
        }
        platforms, trips = parse_timetable(day)
        schedules.append(day | {"headways": summarize_headways(platforms, trips)})
        attribution.update(day["attribution"])
    config = {
        "schema_version": 1,
        "kind": "representative_schedules",
        "timezone": "America/Toronto",
        "reference_dates": reference_dates,
        "schedules": schedules,
        "map_evidence": map_evidence,
        "attribution": sorted(attribution),
    }
    validate_network(config)
    return config


def _statistics(band: dict) -> str:
    if band["median_s"] is None:
        return "—"
    return f"{band['median_s']:g} [{band['min_s']:g}, {band['max_s']:g}]"


def _day_report(day: dict) -> list[str]:
    platforms, trips = parse_timetable(day)
    lookup = {p.platform_id: p for p in platforms}
    lines = [f"## {day['service_date']}", ""]
    for feed in day["feeds"]:
        lines.append(
            f"- {feed['agency']}: `{feed['feed_id']}`, "
            f"version `{feed['feed_version']}`, "
            f"downloaded {feed['downloaded_on']}; feed validity "
            f"{feed['coverage_start']}–{feed['coverage_end']}"
        )
    lines += [
        "",
        f"{len(trips)} trips; {sum(len(t.visits) for t in trips)} interchange visits.",
        "",
        "| Platform / direction | Route | Departures | Early | AM | Midday | "
        "PM | Evening | Late |",
        "|---|---|---:|---|---|---|---|---|---|",
    ]
    for summary in day["headways"]:
        platform = lookup[summary["platform_id"]]
        route = summary["route_id"] or "combined"
        name = f"{platform.stop_name} / {platform.line_id} → {platform.direction_label}"
        count = sum(b["departure_count"] for b in summary["bands"])
        cells = " | ".join(_statistics(b) for b in summary["bands"])
        lines.append(f"| {name} | {route} | {count} | {cells} |")
    lines += [
        "",
        "REM scheduled dwell (seconds, minimum–maximum across physical visits):",
        "",
    ]
    for platform in platforms:
        if platform.line_id != "rem":
            continue
        dwell = [
            v.departure_s - v.arrival_s
            for t in trips
            for v in t.visits
            if v.platform_id == platform.platform_id
        ]
        value = f"{min(dwell)}–{max(dwell)}" if dwell else "unavailable (no visits)"
        lines.append(f"- {platform.stop_name}, {platform.direction_label}: {value}")
    return lines + [""]


def render_report(config: dict) -> str:
    """Validate config and render its Markdown report."""
    validate_network(config)
    lines = [
        "# Representative interchange schedules (#88)",
        "",
        "These are three dated representative schedules, not full calendar coverage.",
        "Timezone: America/Toronto. Times stay in their originating service day "
        "beyond midnight.",
        "",
        "Boarding-eligible headways: median [minimum, maximum] in seconds; "
        "— means no gap.",
        "Each gap belongs to its later departure's band, "
        "including gaps across band boundaries.",
        "Combined frequency does not promise a common passenger destination.",
        "",
        "Bands: early <06:00; AM 06:00–09:00; midday 09:00–15:00; PM 15:00–18:00; "
        "evening 18:00–21:00; late ≥21:00.",
        "",
    ]
    lines.extend(
        f"- {label}: {config['reference_dates'][label]}"
        for label in ("weekday", "saturday", "sunday")
    )
    lines.append("")
    for day in config["schedules"]:
        lines.extend(_day_report(day))
    lines += ["## Map verification", ""]
    lines.extend(
        f"- [{e['url']}]({e['url']}), checked {e['checked_on']}: {e['notes']}"
        for e in config["map_evidence"]
    )
    lines += ["", "## Attribution", "", *config["attribution"], ""]
    return "\n".join(lines)


def write_config(config: dict, output_dir: Path) -> None:
    """Publish JSON and report together in a new directory.

    Skip identical output; reject existing output that differs.
    """
    validate_network(config)
    content = (
        json.dumps(
            config, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False
        )
        + "\n"
    )
    report = render_report(config)
    files = {"network.json": content, "report.md": report}
    if output_dir.exists():
        if output_dir.is_dir() and all(
            (output_dir / name).is_file()
            and (output_dir / name).read_bytes() == text.encode("utf-8")
            for name, text in files.items()
        ):
            return
        raise ValueError(
            "output directory already exists with different data; "
            "choose a new --output-dir"
        )
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".network-", dir=output_dir.parent) as work:
        staging = Path(work) / "bundle"
        staging.mkdir()
        for name, text in files.items():
            (staging / name).write_text(text, encoding="utf-8", newline="\n")
        load_network(staging / "network.json")
        staging.rename(output_dir)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--weekday", type=date.fromisoformat, default=date(2026, 10, 5))
    parser.add_argument(
        "--saturday", type=date.fromisoformat, default=date(2026, 10, 10)
    )
    parser.add_argument("--sunday", type=date.fromisoformat, default=date(2026, 10, 11))
    args = parser.parse_args(argv)
    configure_logging()
    references = {
        name: getattr(args, name) for name in ("weekday", "saturday", "sunday")
    }
    logger.info("Starting reference extraction: dates=%s", references)
    try:
        if (
            references["weekday"].weekday() > 4
            or references["saturday"].weekday() != 5
            or references["sunday"].weekday() != 6
        ):
            raise ValueError(
                "reference dates must match weekday/Saturday/Sunday labels"
            )
        _load_local_connection_settings()
        previews = read_schedules(
            load_mapping(DEFAULT_MAPPING), tuple(references.values())
        )
        config = build_config(
            previews, {k: v.isoformat() for k, v in references.items()}, MAP_EVIDENCE
        )
        write_config(config, args.output_dir)
        logger.info("Reference extraction completed: schedules=%d", len(previews))
    except (ValueError, SupabaseReadError) as error:
        logger.error("Reference extraction failed: %s", error)
        return 1
    except OSError:
        logger.error(
            "Could not save configuration; check output path and permissions. "
            "Prior output was preserved.",
        )
        return 1
    print(f"Saved three reference schedules and report under {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
