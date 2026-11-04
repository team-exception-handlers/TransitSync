# AI contribution: 50% or more AI-generated
"""Set up simulation runs for the train holding tests.

Use fresh trains and check settings before each run.
Use the same minimum train gap for checks and movement.
"""

import json
from collections.abc import Collection, Mapping, Sequence
from datetime import date
from pathlib import Path
from typing import Any

from simulator.control.decision import DecisionPipeline
from simulator.control.headway_configuration import validate_headway_configuration
from simulator.control.rules import OperatingRulesEnforcer
from simulator.control.strategies import STRATEGIES
from simulator.engine.random_streams import StreamManager
from simulator.engine.runner import RunResult, run_scenario
from simulator.scenario import (
    DatasetMetadata,
    Scenario,
    load_scenario_json,
)
from simulator.trains.suspension import LineSuspension
from simulator.trains.train import ScheduledStop, Train
from simulator.trains.train_component import TrainComponent


def scenario_input(
    strategy: str = "headway_regulation", target: object = 300, scenario_gap: float = 60
) -> dict[str, Any]:
    """Build fresh scenario values with a fixed date and seed.

    Custom search settings catch lost values during saving or loading.
    The search cap does not limit headway holds.
    Allow invalid targets so tests can check the loader's errors.
    """
    control: dict[str, Any] = {
        "strategy": strategy,
        "hold_search": {"step_s": 10, "max_hold_s": 90},
        "weights": {"w_wait": 1.5, "w_onboard": 0.75},
    }
    if strategy == "headway_regulation":
        control["target_headways_s"] = {"P": target}
    return {
        "dataset_id": "test",
        "date": "2026-10-05",
        "start_time": "07:00",
        "duration_s": 600,
        "master_seed": 7,
        "interchanges": ["mcgill"],
        "control": control,
        "operating_rules": {"min_safe_gap": scenario_gap, "max_hold_time": 300},
    }


def load(values: dict[str, Any]) -> Scenario:
    """Load a scenario with local test metadata.

    The fixed date keeps service checks repeatable.
    Let the test receive any validation errors.
    """
    dataset = DatasetMetadata(
        "test",
        date(2026, 10, 5),
        date(2026, 10, 5),
        {"mcgill": 86400},
        frozenset({"mcgill"}),
    )
    return load_scenario_json(json.dumps(values), {"test": dataset})


def run_selected(
    output_dir: Path,
    values: dict[str, Any],
    *,
    engine_gap: float = 90,
    trains: Sequence[Train] | None = None,
    catalog: Collection[str] | None = None,
    suspensions: Sequence[LineSuspension] = (),
) -> RunResult:
    """Validate settings, then run the saved policy.

    Build a fresh strategy from the loaded settings.
    Check all supplied trips and platforms before components start.
    Use the same minimum gap for validation and movement.
    Callers must supply fresh trains for each run.
    Gap and suspension times are in seconds.
    Return output paths; let validation and run errors reach the test.
    """
    scenario = load(values)
    if trains is None:
        trains = [
            Train("A", 800, (ScheduledStop("S", "P", 170, 200),)),
            Train("B", 800, (ScheduledStop("S", "P", 370, 400),)),
        ]
    if catalog is None:
        catalog = {"P"}

    def build_components(settings: Scenario, _streams: object) -> list[TrainComponent]:
        validate_headway_configuration(settings.control, trains, catalog, engine_gap)
        policy = STRATEGIES.build(
            settings.control.strategy,
            target_headways_s=settings.control.target_headways_s,
        )
        return [
            TrainComponent(
                trains,
                minimum_gap_s=engine_gap,
                suspensions=suspensions,
                decision=DecisionPipeline(
                    policy, enforcer=OperatingRulesEnforcer(settings.operating_rules)
                ),
            )
        ]

    return run_scenario(scenario, StreamManager, build_components, output_dir)


def event_tuples(
    records: Sequence[Mapping[str, Any]], event_type: str, fields: Sequence[str]
) -> list[tuple[Any, ...]]:
    """Collect every matching event, including duplicates.

    Preserve log order so tests can check event order.
    """
    return [
        tuple(record[field] for field in fields)
        for record in records
        if record["event_type"] == event_type
    ]
