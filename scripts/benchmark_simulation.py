# AI contribution: 50% or more AI-generated
"""Measure uncached API runs and profile the complete station-view response.

The API is synchronous: backend response time is a lower bound on browser
click-to-display latency. Results time starts when run_scenario returns and
ends after HTTP serialization; rendering and transport are outside this probe.
No production settings, cache policy, or response fields are changed.
perf_counter measures elapsed wall time, including I/O and serialization, rather
than just CPU time. Each fresh application excludes cache hits between samples.
The worker-thread profile is separate from these timings because tracing itself
adds substantial overhead. Response hashes and optional full captures protect
output equivalence independently of any timing target.
"""

import argparse
import cProfile
import ctypes
import hashlib
import json
import platform
import shutil
import statistics
import subprocess
from dataclasses import replace
from datetime import time
from pathlib import Path
from time import perf_counter
from unittest.mock import patch

from fastapi.testclient import TestClient

import api.simulation_run as simulation_run
from api.main import create_app
from simulator.control.strategies import STRATEGIES


def _peak_memory_bytes():
    """Return the process high-water RSS, without a profiling dependency.

    Windows exposes this through PSAPI; Linux reports KiB through getrusage.
    macOS reports bytes. These are process peaks, not allocation snapshots.
    """
    if platform.system() != "Windows":
        import resource

        peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return peak if platform.system() == "Darwin" else peak * 1024

    class MemoryCounters(ctypes.Structure):
        _fields_ = [("size", ctypes.c_ulong), ("faults", ctypes.c_ulong)] + [
            (name, ctypes.c_size_t)
            for name in (
                "peak",
                "working",
                "qpeak",
                "q",
                "ppeak",
                "p",
                "page",
                "pagepeak",
            )
        ]

    counters = MemoryCounters()
    counters.size = ctypes.sizeof(counters)
    handle = ctypes.c_void_p(ctypes.windll.kernel32.GetCurrentProcess())
    success = ctypes.windll.psapi.GetProcessMemoryInfo(
        handle, ctypes.byref(counters), counters.size
    )
    if not success:
        raise ctypes.WinError()
    return counters.peak


def measure(strategy, *, full_day=False, capture=None, changed=False, profiler=None):
    """Return seconds and response fingerprint for one fresh, uncached request.

    A full service day starts at midnight and includes the feed's final service
    timestamp, including GTFS times beyond 24:00. Override duration_s directly,
    leaving the API's one-hour default and request schema intact.
    Optional capture preserves exact logs and response bytes for regression QA.
    """
    if capture is not None:
        # Python callers must obey the same artifact boundary as the CLI.
        capture = capture.resolve()
        if not capture.is_relative_to(Path.cwd().resolve()):
            raise ValueError("capture must be inside the repository")
    original_load = simulation_run.SimulationRunService._load_scenario
    original_run = simulation_run.run_scenario
    original_service_run = simulation_run.SimulationRunService.run
    timing = {}

    def load(service, *args, **kwargs):
        """Override only this experiment's immutable scenario after validation.

        The feed boundary includes after-midnight GTFS departures. Keep the
        original date and timezone so the selected service remains unchanged.
        """
        scenario = original_load(service, *args, **kwargs)
        if full_day:
            end_s = service._dataset.service_day_end_s_by_interchange[
                scenario.interchanges[0]
            ]
            scenario = replace(
                scenario,
                duration_s=end_s,
                start_time=time(),
                resolved_start=scenario.resolved_start.replace(hour=0),
            )
        timing["duration_s"] = scenario.duration_s
        timing["scenario"] = scenario.to_dict()
        return scenario

    def run(*args, **kwargs):
        """Mark completion before playback adaptation starts, in seconds.

        Copying optional regression artifacts is excluded from the results
        phase; capture runs are separate from the published latency samples.
        """
        started = perf_counter()
        result = original_run(*args, **kwargs)
        timing["simulation_s"] = perf_counter() - started
        if capture is not None:
            capture.mkdir(parents=True, exist_ok=True)
            for source in (result.events_path, result.decisions_path):
                shutil.copyfile(source, capture / source.name)
        timing["completed_at"] = perf_counter()
        return result

    def service_run(service, request):
        """Profile the actual endpoint worker, including its response cache dump."""
        # FastAPI executes synchronous routes in a worker thread. Start cProfile
        # there; profiling the TestClient caller would miss the simulation.
        if profiler is not None:
            return profiler.runcall(original_service_run, service, request)
        return original_service_run(service, request)

    settings = {
        "connection_id": "mcgill-rem-green",
        "strategy": strategy,
        "max_hold_time": 120 if changed else 300,
    }
    if strategy == "adaptive":
        settings["irregularity_threshold"] = 0.2
    # Construct static configuration before timing a user's request; a new app
    # prevents result-cache hits from masquerading as faster simulation work.
    with patch.object(simulation_run.SimulationRunService, "_load_scenario", load):
        with patch.object(simulation_run, "run_scenario", run):
            with patch.object(simulation_run.SimulationRunService, "run", service_run):
                with TestClient(create_app()) as client:
                    if changed:
                        # Prime this same service with the previous settings;
                        # time only the different, uncached parameter request.
                        previous = {**settings, "max_hold_time": 300}
                        client.post("/simulation/run", json=previous).raise_for_status()
                    started = perf_counter()
                    response = client.post("/simulation/run", json=settings)
                    finished = perf_counter()
    response.raise_for_status()
    if capture is not None:
        (capture / "response.json").write_bytes(response.content)
    return {
        "strategy": strategy,
        "settings": settings,
        "scenario": timing["scenario"],
        "duration_s": timing["duration_s"],
        "request_s": finished - started,
        "simulation_s": timing["simulation_s"],
        "results_s": finished - timing["completed_at"],
        "response_bytes": len(response.content),
        "response_sha256": hashlib.sha256(response.content).hexdigest(),
        "peak_memory_bytes": _peak_memory_bytes(),
    }


def main():
    """Print individual timings, median/range, environment and optional profile.

    Run as python -m scripts.benchmark_simulation from the repository root.
    Profiling is a separate run so its overhead never enters the baseline.
    Every completed sample is kept, including slow ones; median and range use
    the same raw observations printed to stdout and saved for later review.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strategy", choices=STRATEGIES.names(), required=True)
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--full-day", action="store_true")
    parser.add_argument("--changed", action="store_true")
    parser.add_argument("--capture", action="store_true")
    parser.add_argument("--profile", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error("--repeats must be positive")
    root = Path.cwd().resolve()
    output = args.output.resolve()
    if not output.is_relative_to(root):
        parser.error("--output must be inside the repository")
    output.mkdir(parents=True, exist_ok=True)
    measurements = []
    for index in range(args.repeats):
        result = measure(args.strategy, full_day=args.full_day, changed=args.changed)
        measurements.append(result)
        print(json.dumps({"repeat": index + 1, **result}), flush=True)
        # Preserve completed observations even if a later expensive run is
        # interrupted. These are raw measurements, never substituted estimates.
        (output / "samples.json").write_text(
            json.dumps(measurements, indent=2) + "\n", encoding="utf-8"
        )
    summary = {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True
        ).strip(),
        "measurements": measurements,
        "median_s": statistics.median(r["request_s"] for r in measurements),
        "range_s": [
            min(r["request_s"] for r in measurements),
            max(r["request_s"] for r in measurements),
        ],
    }
    if args.profile:
        profiler = cProfile.Profile()
        started = perf_counter()
        profiled = measure(
            args.strategy,
            full_day=args.full_day,
            changed=args.changed,
            profiler=profiler,
        )
        summary["profiled_s"] = perf_counter() - started
        summary["profiled_request_s"] = profiled["request_s"]
        summary["profile_overhead_ratio"] = profiled["request_s"] / summary["median_s"]
        profiler.dump_stats(output / "run.pstats")
    if args.capture:
        measure(
            args.strategy,
            full_day=args.full_day,
            changed=args.changed,
            capture=output / "contract",
        )
    (output / "measurements.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary), flush=True)


if __name__ == "__main__":
    main()
