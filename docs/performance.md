# Simulation performance

For the current-main integration and task acceptance audit, see
[Performance task readiness](performance-readiness.md). The measurements below
describe the earlier base and are retained as historical before/after evidence.

These local changes use main `8ddf153ecbbe29326658deefaa685a586b6a38ff` as
the reference. They preserve the one-hour API default, response schema, random
draw order, hold grid, planning window, search budget, and audit fields.
No new dependency is required. Related investigation: #395.

## Architecture and Iteration 5

TransitSync evaluates whether short Metro/REM train holds save transferring
passengers more time than they cost onboard passengers and later services.
FastAPI validates a request and loads a committed scenario. Fresh components
process seeded train and passenger events through the heap-based event queue.
The runner writes movements and decisions; the API derives passenger tracks,
adapts the station view, caches the response and serializes it for React playback.

No-control proposes no holds. Schedule-based holding aligns early departures
with the timetable; headway regulation targets departure gaps. Connection
protection weighs saved passenger waiting against delay costs. Adaptive switches
between connection protection and headway regulation. Coordinated evaluates
future holds over a rolling window and applies only the current action before
replanning from a fresh immutable observation.

Iteration 5 adds passenger outcomes, paired comparisons, results statistics,
configurable scenarios and data provenance. Pairing and replications multiply
simulation work; longer runs magnify audit storage and playback preparation.
These performance changes keep those contracts intact and localize edits to
profiled functions. They do not implement the other teams' features.

## What is measured

The [Performance wiki](https://github.com/team-exception-handlers/TransitSync/wiki/Performance)
defines startup as clicking Start through the first displayed simulation state,
parameter updates as confirmation through availability of the updated state,
and results as simulation completion through display. The current endpoint is
synchronous: its response must arrive before the UI can show a simulated state.

The Python tests measure necessary backend bounds, **not browser certification**:

| Operation | Backend measurement | Limit |
|---|---|---|
| Startup | Uncached in-process HTTP request through serialized response bytes | 2 s |
| Parameter update | Prime one service, change maximum hold from 300 to 120 s, time the uncached request | 1 s |
| Results | Return from `run_scenario` through log reading, tracks, response construction, cache serialization and HTTP bytes | 2 s |
| Full service day | Uncached HTTP request through complete station-view response | 30 s |

Application creation and static network loading precede request timing. Each
sample gets a fresh application, so no result-cache hit is counted. The parameter
test primes that same application outside the measured interval. Full-day runs
start at midnight and set `Scenario.duration_s` directly to the feed's final
service timestamp at McGill: 92,576 s, including service beyond 24:00. The
production request and committed scenario files are unchanged.

All six registered strategies use McGill, the committed weekday schedule, seed
42, Normal demand and prediction-error magnitude 1. Adaptive uses threshold
0.2. Ordinary requests retain the default maximum hold of 300 s. These runs
include the reference network's other trains, as production does. Browser
transport, parsing and drawing need a separate click-to-display measurement.

The comparison endpoint is not present in this base. Single-run measurements
must not be presented as measurements of that future endpoint; compare its
chosen strategy plus No-control when that implementation lands. Keyed paired-run
random draws (#191/#192) remain separate work.

## Measured results

Measured on Windows 11, CPython 3.13.2, NumPy 2.5.4, FastAPI 0.162.0,
Pydantic 2.14.3, 12 logical processors and 15.9 GiB RAM. These are local
workstation measurements, not a guarantee for CI or browser display latency.
The Windows sandbox prevents asyncio socketpair creation; TestClient
measurements were run outside it. Native request timings exclude process
startup. The service-day duration is 92,576 s. See
`performance-results.json` for every individual timing and response digest.

Hourly columns are medians of five unprofiled runs. Parameter changes and
full days have one completed sample per strategy. No slow sample was removed.
Unfinished experiments have no measured completion time; their worker deadline
includes process/application startup and, for changed parameters, the untimed priming request.
They fail the benchmark experiment; no missing completion time is substituted.

| Strategy | Startup before (s) | Startup after (s) | 2 s backend bound |
|---|---:|---:|---|
| no_control | 5.880 | 2.347 | Fail |
| schedule_based | 5.995 | 2.287 | Fail |
| headway_regulation | 5.790 | 2.306 | Fail |
| connection_protection | 5.842 | 2.307 | Fail |
| adaptive | 5.910 | 2.342 | Fail |
| rolling_horizon | unfinished (120 s worker limit) | unfinished (120 s worker limit) | Unfinished |

| Strategy | Parameters before (s) | Parameters after (s) | 1 s backend bound |
|---|---:|---:|---|
| no_control | 5.673 | 2.281 | Fail |
| schedule_based | 5.818 | 2.274 | Fail |
| headway_regulation | 5.888 | 2.242 | Fail |
| connection_protection | 5.710 | 2.283 | Fail |
| adaptive | 5.759 | 2.259 | Fail |
| rolling_horizon | unfinished (60 s worker limit) | unfinished (60 s worker limit) | Unfinished |

| Strategy | Hourly results before (s) | Hourly results after (s) | 2 s backend bound |
|---|---:|---:|---|
| no_control | 0.675 | 0.237 | Pass |
| schedule_based | 0.715 | 0.235 | Pass |
| headway_regulation | 0.693 | 0.236 | Pass |
| connection_protection | 0.695 | 0.243 | Pass |
| adaptive | 0.701 | 0.236 | Pass |
| rolling_horizon | unfinished (120 s worker limit) | unfinished (120 s worker limit) | Unfinished |

| Strategy | Full day before (s) | Full day after (s) | 30 s target | Results phase after (s) |
|---|---:|---:|---|---:|
| no_control | 95.881 | 29.348 | Pass | 3.870 |
| schedule_based | 85.861 | 29.569 | Pass | 3.839 |
| headway_regulation | 85.930 | 30.160 | Fail | 4.052 |
| connection_protection | 88.950 | 30.447 | Fail | 3.837 |
| adaptive | 87.626 | 30.117 | Fail | 3.782 |
| rolling_horizon | unfinished (120 s worker limit) | unfinished (120 s worker limit) | Unfinished | unfinished (120 s worker limit) |

Full-day No-control peak resident memory fell from **6.59 GiB to 0.73 GiB**.
All completed hourly, changed-parameter and full-day responses match the
original response SHA-256 exactly for every strategy that completed. The
Coordinated full-request cases remain unfinished at their deadlines; only
the separately captured planning observation and seeded regression runs have
complete before/after results for that strategy.

Unmet and unverified targets remain explicit. No browser target is certified. The full-day
results phase also exceeds its separate 2 s target. Faster first-state delivery
must not be claimed by timing only component initialization, cache hits or an
incomplete response. The Coordinated search needs further measured work at its
existing budget; reducing the grid or budget would change its behavior.

## Reproduce

Use the repository Python environment and run from its root:

```powershell
python -m pytest tests/performance -m performance -s
python -m pytest tests/performance -m performance -s -k "full_day and no_control"
python -m pytest tests/performance -m performance -s --performance-timeout=300
python -m scripts.benchmark_simulation --strategy no_control --repeats 5 --profile --output .benchmarks/no-control
python -m scripts.benchmark_simulation --strategy rolling_horizon --repeats 5 --output .benchmarks/coordinated
python -m scripts.benchmark_simulation --strategy no_control --full-day --repeats 1 --profile --output .benchmarks/full-day
python -m scripts.benchmark_simulation --strategy adaptive --changed --repeats 5 --output .benchmarks/parameter-change
python -m scripts.benchmark_simulation --strategy no_control --repeats 1 --capture --output .benchmarks/contract
python -m pstats .benchmarks/no-control/run.pstats
```

Performance tests are marked `performance` and excluded by the default pytest
selection. The developer benchmark CLI is excluded from Sonar coverage because
its live measurements are deliberately outside ordinary CI; production code
coverage exclusions and quality thresholds are unchanged. They retain strict assertions: slow work is not xfailed. Their worker
budget bounds unfinished experiments; it does not relax any target. Timeouts are
reported as unfinished, without inventing a completion time. Increase the budget
for longer investigations. CLI runs deliberately have no deadline and can take
minutes for Coordinated; completed samples are saved incrementally.

The CLI prints individual samples, median and range, actual scenario settings,
response SHA-256, response size, process peak resident memory (the most RAM held by Python) and runtime versions.
`--profile` runs separately from the unprofiled samples. It starts cProfile in
FastAPI's synchronous worker thread; profiling only the TestClient thread would
miss the simulation. The profile covers simulation, audit encoding/writing, log
reading, tracks, response construction and cache serialization. HTTP wall time
also includes FastAPI's final response serialization. `--capture` performs an
additional untimed-for-reporting run to retain exact response/event/audit files;
capture copying is not included in published timing samples.

Output directories must resolve inside the repository. Generated profiles,
captures, samples and reference snapshots stay in ignored `.benchmarks/`.

## Profile findings and changes

The original one-hour No-control profile recorded these nested costs; cumulative
times overlap and must not be added together:

| Function | Calls | Internal time | Cumulative time |
|---|---:|---:|---:|
| `copy.deepcopy` | 4,920,661 including recursive calls | 3.602 s | 8.146 s |
| `_process_events` | 1 | <0.001 s | 5.640 s |
| `PredictionErrorModel.apply` | 195 | 0.048 s | 3.318 s |
| `dataclasses.replace` | 330,874 | 0.203 s | 1.857 s |
| `ObservationBuilder.build` | 195 | 0.002 s | 1.155 s |

Five unprofiled initial No-control samples had median 5.962 s and range
5.825-6.215 s. The separate profiled experiment took 15.329 s, approximately
2.57 times that median including its application setup. Do not compare profiled
times directly with unprofiled API latency.

Estimate records now use the existing compact JSON encoding once at creation.
An immutable value object retains that representation; the writer streams it
without a second encode or full-run deep copy. Public audit readers still return
fresh detached dictionaries, with strategy records preceding estimate records.
The runner retains the original fallback for components exposing only
`decision_records`. Fixed train fields are built directly rather than through
reflective attribute loops. Station-view preparation reads decision JSONL (one JSON record per line) lazily
and uses the existing filters in a single pass. A Pydantic header validates each
whole JSON record while ignoring unused estimate bodies; only estimates for
shown holds allocate complete Python train dictionaries. Mode switches retain
their previous path, and stdlib fallback preserves legacy JSON and corruption
errors. Complete audit files remain intact. Pydantic and pydantic-core are
already installed runtime dependencies; no package or lockfile changes are needed.

Immutable train snapshots with identical typed fields are reused within one
run. The bounded cache is owned by TrainComponent and is recreated for every
scenario. Completed trains remain in observations and consume the same random
draws; only obsolete stop lookups are skipped. Prediction-state copies use the
fixed schema directly, with dataclass replacement retained for subclasses.
Tests check live load/delay updates, retained subclass metadata and unchanged
random-stream position.

The first original Coordinated decision evaluated 41,401 candidates and took
40.239 profiled seconds. Dependency topology and full-network load maps were
rebuilt for every candidate. The optimized planner prepares topology and cost
inputs once per observation and reuses pure projected visits, shifted visits,
local hold values and per-train marginal costs. Candidate order, arithmetic
summation order, tie-breaking, exact/approximate status and audit counts are
preserved. Every new observation gets fresh caches. No station or candidate is
dropped. Passenger track generation already groups events once per passenger;
the profile did not justify changing its sampling or geometry.

Regression hashes were generated with the unmodified reference, not with the
optimized implementation. They cover real transfer runs, prediction errors,
rule clamping, downstream refusal and the bounded approximate search. The
captured production observation also retains the same complete plan digest.

## Review and integration

Keep four review units, each below the repository's 400 changed-source-line cap:

1. `Add opt-in simulation performance benchmarks (#395)` - CLI, marker, performance tests and measurement documentation
2. `Stream encoded simulation decision audits (#395)` - immutable encoded records, pipeline, train adapter, runner and audit regression tests
3. `Reuse coordinated forecast and cost calculations (#61, #62)` - downstream preparation, planner-local reuse and original-output regression hashes
4. `Stream station-view audit preparation (#395)` - JSONL reading, single-pass playback adaptation and full-day validation

Tests, fixtures and documentation do not count toward the source-line cap under
the repository's review rules. Each suggested commit should include an accurate
`AI-assisted: Codex (OpenAI), 50% or more AI-generated` trailer. Measurements and
validation were completed before publication. The changes in `api/simulation_run.py` touch only
the audit reader call and the JSONL reader functions, leaving scenario settings,
cache keys, run orchestration and response schemas intact for parallel work.

Draft Design Patterns wiki addition (local review only):

### Value Object: encoded decision records

- **Where:** `simulator/control/decision_audit.py`, `EncodedDecisionRecord`
- **Problem:** retaining and copying full-network estimate dictionaries at every decision makes complete service-day audits expensive (#395)
- **How:** retain immutable compact JSON after the existing encoder validates finite values; stream it to the log and decode detached dictionaries for public readers
- **Why:** reusing the established immutable Value Object approach preserves exact bytes and public isolation without a new persistence or logging dependency
- **Added in:** local performance changes, PR not opened

Library Comparisons: none; all tools use existing dependencies or Python's
standard library. AI contribution for these changes and this report: 50% or more
AI-generated, Codex (OpenAI).

## Independent validation

`pytest -q`: **1,785 passed, 30 performance cases deselected, one existing
expected failure** for paired prediction-error drift (#191).
`ruff check .`, `ruff format --check .`, and extended rules on every changed
Python file passed. The optional full-repository extended scan still reports
16 pre-existing findings outside the changed files; those findings were not
modified. No frontend source or response schema changed.

The independent opt-in suite was run with a 45 s worker budget: **5 passed,
21 failed and 4 setup errors** in 353.60 s. The setup errors come from two
Coordinated fixtures that each serve two checks and could not finish. The
Coordinated parameter experiment also timed out. Remaining failures are the
strict latency assertions, not simulation exceptions or weakened tests.

| Strategy | Independent full-day request (s) | Results phase (s) | 30 s target |
|---|---:|---:|---|
| adaptive | 33.776 | 4.198 | Fail |
| connection_protection | 32.585 | 3.907 | Fail |
| headway_regulation | 33.090 | 4.087 | Fail |
| no_control | 30.514 | 3.906 | Fail |
| schedule_based | 33.144 | 4.041 | Fail |

**The full-day target is not reliably met.** Two single-sample matrix runs
were below 30 s, but all five independent full-day checks exceeded it. Retain
both sets of observations; do not select only the passing samples. Startup,
parameter updates and full-day result preparation also remain above target.
Browser click-to-display latency and the absent comparison endpoint remain
unmeasured. All 15 completed independent responses match the original hashes.

Next work should focus on the remaining full-network observation/prediction
cost and the per-candidate Coordinated scoring loop. Any batched random draws
need exact stream-position and output equivalence tests before use. A compact
API audit projection produced alongside the complete log could reduce the
remaining results scan, but its interface should be agreed with comparison
and results work. The current code retains complete logs and existing public
dictionary readers.


## Measured optimization stages

The No-control full-day experiments used the same settings and retained the
same response digest throughout:

| Stage | API request (s) | Simulation (s) | Results (s) |
|---|---:|---:|---:|
| Unmodified reference | 95.881 | 84.538 | 11.329 |
| Encoded audits, streaming adaptation and initial copies | 39.357 | 31.311 | 8.034 |
| Snapshot reuse, fixed-field audit construction and native decoding | 32.391 | 26.456 | 5.923 |
| Header filtering probe | 29.398 | 25.298 | 4.088 |
| Final matrix sample | 29.348 | 25.465 | 3.870 |

These are individual full-day observations, not isolated estimates of each
change's effect. Independent validation above records the additional slower
samples. The same captured Coordinated planning observation was measured five
times per version: median **22.272 s before, 2.332 s after**, with ranges
21.223-22.800 s and 2.259-2.468 s. All ten results have the same complete-plan
digest and exactly 41,401 evaluations. This is a planner-only benchmark, not a
completed one-hour or comparison request.

On a saved 49,385,217-byte audit, five decoder microbenchmarks measured stdlib
JSON at 0.395-0.419 s, the existing native decoder at 0.235-0.291 s, and a
header-only model at 0.143-0.163 s. This motivated the native/header paths;
syntax corruption and unsupported legacy strings retain the stdlib fallback.
An extra component-level projection cache showed no meaningful improvement in
the captured decision and was removed rather than retained as extra complexity.


## Files changed

| File | Purpose |
|---|---|
| `scripts/benchmark_simulation.py` | Uncached HTTP measurements, phase boundaries, profiles, captures and process-memory reporting |
| `pyproject.toml` | Register and exclude the opt-in performance marker by default |
| `.gitignore` | Keep generated benchmark artifacts out of the source diff |
| `sonar-project.properties` | Exclude only the standalone developer benchmark CLI from ordinary CI coverage |
| `simulator/control/decision.py` | Retain encoded immutable estimates and preserve detached public audit readers |
| `simulator/control/decision_audit.py` | Encode once, construct fixed train fields directly and stream unchanged audit bytes |
| `simulator/engine/runner.py` | Prefer streamed encoded records while retaining the existing audit-source fallback |
| `simulator/trains/train_component.py` | Expose the writer path and reuse immutable typed snapshots within a run |
| `simulator/control/downstream.py` | Prepare dependency topology and marginal-cost inputs once per observation |
| `simulator/control/rolling_horizon.py` | Reuse pure candidate calculations without changing search order or counts |
| `simulator/control/prediction_error.py` | Copy the standard train schema directly and retain subclass fallback |
| `api/simulation_run.py` | Stream JSONL, reuse the native decoder and allocate only audit bodies needed by playback |
| `api/station_view.py` | Adapt estimates and mode switches in one pass |
| `tests/performance/conftest.py` | Independent, configurable worker budget |
| `tests/performance/runner.py` | Isolate measurements and report unfinished experiments explicitly |
| `tests/performance/test_simulation_performance.py` | Strict startup, parameter, results and full-day targets for all six strategies |
| `tests/api/test_audit_streaming.py` | Check single-pass equivalence, JSON compatibility and corruption errors |
| `tests/scripts/test_benchmark_simulation.py` | Reject capture paths outside the repository before starting work |
| `tests/simulator/control/test_estimate_storage.py` | Check exact bytes and detached mutable readers |
| `tests/simulator/control/test_coordinated_performance_regression.py` | Protect original event/audit digests across exact/approximate decisions and rules |
| `tests/simulator/control/test_prepared_forecasts.py` | Compare reused forecasts/costs with standalone arithmetic and fresh observations |
| `tests/simulator/control/test_prediction_copy.py` | Protect subclass metadata and random-stream position |
| `tests/simulator/trains/test_snapshot_reuse.py` | Check live load and delay changes remain visible |
| `AI_USAGE.md` | Declare AI-assisted files and verification evidence |
| `docs/performance.md` | Record architecture, methods, results, validation and remaining targets |
| `docs/performance-results.json` | Preserve actual individual measurements and response digests |
