# Person 5: coordinated strategies

Historical report for the preserved two-commit branch
`feat/61-person-5-coordinated-strategies`. The current review branches and
validation results are described in the corresponding pull requests.

## Requirements and architecture

Read the full issues, comments and timelines for #61, #62, #43, #63 and #64,
parent stories #36 and #32, and dependency PR #155 (including reviews).
Neither #61 nor #62 has additional comments or acceptance checklists.
Adaptive switching (#63/#64) remains outside this implementation.

| Issue requirement | Implementation and verification |
|---|---|
| #61: define the forward window | `RollingHorizonSettings.window_s`; default 300 seconds is an explicit assumption, configurable and saved in manifests |
| #61: enumerate hold combinations at all stations in the window | Exact Cartesian product using #43's `HoldSearchSettings`; three-station, inclusive-boundary and budget tests |
| #61: apply first decision, then re-plan | `RollingHorizonStrategy` returns only the current train's action; changed-observation and real-run tests |
| #62: project subsequent-station effects | Pure `project_visits` forecast, validated against actual engine departures over three stations and a return trip |
| #62: reject locally helpful, globally harmful holds | Marginal downstream cost in joint objective; +300 local / 5000 downstream unit and complete-run regression tests |

The heap-based event engine calls `DecisionPipeline` at each `DepartureDue`.
The pipeline builds an immutable observation, applies prediction error, calls
the strategy, then submits its request to an enforcer. TrainComponent owns
movement, platform occupancy/separation and load changes. TransferComponent
generates train-triggered groups and individual walks; PlatformQueue owns
boarding and passenger journeys. The runner collects `decisions.jsonl` through
the existing `DecisionAuditSource` protocol.

Existing production strategies are no control, schedule-based holding and
headway regulation. Break-even search and audit utilities are separate;
predictive connection protection is another task. #43 introduced configurable
candidate durations, exhaustive local objective evaluation, the zero option
and shorter-hold tie breaking. PR #155 merged that dependency to `main` on
2026-11-03 (merge `317e280defb1b6eda712cba1de81f7d0d4ccf599`).

## Using rolling-horizon planning

Select `control.strategy = "rolling_horizon"`. Optional
`control.rolling_horizon` accepts `window_s` and `max_combinations` (default
100000). Existing `control.hold_search` and `control.weights` still apply.
No new dependencies or event schema changes are needed.

The repository still uses caller-provided component factories. In that factory,
build the policy with `STRATEGIES.build(control.strategy,
walking_by_platform=walking_cdfs, rolling_horizon=control.rolling_horizon,
hold_search=control.hold_search, weights=control.weights)`. Supply CDFs from
the actual transfer-route parameters, keyed by connecting platform. Pass an
`ObservationBuilder([transfers])` and the run's rule enforcer to
`DecisionPipeline`. The pipeline requests full visits only for this strategy.

The forward view retains immutable timetable identities, future stops, return
trips, terminal recovery and fixed decisions already in progress. Additional
future arrival estimates pass through the prediction-error model. The planner
reuses #41's difference of CDFs and #42's passenger-second objective. It values
saved waiting with the next known departure, including one outside the window;
without that information the benefit is zero. No headway or walk is invented.

All window decisions receive the complete candidate grid, including stations
without local transfers: their holds can shift a later connection window.
Overlapping walking intervals are credited once. Ties prefer less total holding,
then shorter durations in current-first order. Enumeration is streamed and fails
clearly before exceeding its configured budget; it never silently drops stations.

## Limits and related findings

Only transfer groups present in the observation are forecast. Future stochastic
demand, unknown destinations, corridor congestion and future load changes are
not invented. Walking estimates inherit #41's corridor-queueing limitation.
The three hundred second window should be tuned against representative runs;
exact combination count grows exponentially with actionable decisions.

Issue #191 documents existing paired-run prediction-error drift. This work does
not replace the random-stream design. Issue #195 documents incomplete default
safety wiring on main: factories should supply OperatingRulesEnforcer; this work
preserves that separation and verifies a clamp through the real pipeline.

## Downstream evaluation (#62)

`simulator/control/downstream.py` projects arrival, departure readiness and actual
departure for every known visit inside the window. Route and platform predecessor
dependencies are evaluated in topological order. This is a deterministic ordering
of the existing movement recurrences, not a new optimization algorithm.
Platform occupancy uses the same next-representable-time boundary as the engine;
minimum gaps come from the actual TrainComponent, not a separate strategy setting.
The existing `dispatch_ready_s` supplies half-open suspension semantics.
Return trips consume only remaining layover slack. Already observed arrivals
stay fixed, and already scheduled arrival waits/injections enter the copied view.

Each candidate is compared to the same zero-hold forecast. Existing disruption
or congestion is therefore not charged to the new hold. Onboard cost charges
only increases in carried delay, subtracting explicit holds already charged by
the local `L*h*w_onboard` formula. For example, a follower's 100 riders delayed
10 seconds over three stations contribute 1000 passenger-seconds, not 3000.
An observed platform queue contributes its added wait at its first service with
available estimated capacity, once per platform, using the existing `w_wait`.
Both forecasts are clipped to the same forward boundary for downstream costs.
Explicit local holds are valued for their full requested duration as in #43.
Decisions moved beyond the window are deferred until a later re-plan.

The planner selects points and headways from feasible baseline departures and
values future local connection windows at their projected decision times. Audit
records include local gain, downstream cost, net gain and the best future
completion for each current hold duration. Rejections can therefore be checked
without storing every combination. No other strategy's objective is changed.

The forecast uses observed load estimates as constant passenger counts. It does
not infer future destination alighting, stochastic feeder bursts or unobserved
disruptions. Existing walking groups are valued with the established CDF formula;
unknown downstream transfer demand is not assigned an invented missed-connection
penalty. These are finite-window estimates, not claims of full-day optimality.

## Local workflow and validation

Original checkout: `feat/75-playback-speed-connections`, clean.
Verified integration base: `origin/main` at
`5fef4e4b645241cbb8682690031c6cf27f890a96`.
Local branch: `feat/61-person-5-coordinated-strategies`, following the wiki's
type/issue/short-name convention. Exactly one local commit per issue is required
by the task; no push, merge, issue edit or PR creation is authorized.

Untouched simulator/scripts baseline: 1377 passed, one existing xfail (#192).
API baseline: 22 passed after installing already-pinned requirements.
Issue #61 full validation: 1430 passed, one existing xfail; Ruff lint and
formatting, simulator compilation and `git diff --check` passed.
Final validation after #62: 1457 passed, one existing xfail (#192), in 29.12 s.
Combined statement/branch coverage of the planner and downstream evaluator is
96% (individual reports: 97% and 96%). All final lint, format, compilation and
whitespace checks passed. This adds 58 passing test cases over the verified
1399-test baseline including API tests; no tests were weakened or disabled.
Use a workspace `--basetemp` on this Windows host; the default temporary folder
is inaccessible inside the sandbox. The API TestClient also requires execution
outside the sandbox on this host. No tests or requirements were weakened.

New #61 tests cover all stations, window boundaries, replanning, exact budget
failure, tie breaking, local-search parity, overlapping groups, frozen snapshots,
return recovery, ongoing holds, prediction error, registry/settings round trips,
real pulsed transfers, rule clamping and byte-identical events/decisions.
The scenario validation regression now includes the newly registered strategy
in its expected list of choices.

Issue #62 adds hand-calculated tests for recursive propagation, marginal onboard
costs, queue costs, zero and missing data, suspension crossings, boundary clipping,
terminal recovery, alternative hold lengths, invalid inputs, full vehicles and
collection-order independence. Generated hold lengths check nondecreasing
departures, occupancy and minimum separation. Integration tests compare forecasts
to real events for 0, 10 and 100-second holds and demonstrate the harmful-hold
rejection in a complete run. A previous local-only overlap test now verifies
connection valuation after the physical departure forecast is applied.
The coupled-search regression also verifies that an upstream hold with no local
transfer group can enable a later station's connection. Every station therefore
keeps the full grid once downstream timing is included; local-only pruning would
miss that combination.

Commands executed (using `.venv/Scripts/python.exe`):

- `-m pytest tests/simulator tests/scripts -q --basetemp=.local/person5-baseline`
- `-m pytest tests/api -q --basetemp=.local/person5-api-baseline`
- Focused tests for each issue before its commit
- `-m pytest -q --basetemp=.local/person5-coupled-final --cov=simulator.control.downstream --cov=simulator.control.rolling_horizon --cov-branch --cov-report=term-missing`
- `-m ruff check .` and `-m ruff format --check .`
- Extended Ruff rules on changed Python files: `PT012,PT018,A001,A002,C420,TRY400`
- `-m compileall -q simulator` and `git diff --check`

No Python type-checking or packaging-build command is configured. The changes
do not touch the web application; compilation and the full Python CI suite
validate this simulator change. Coverage files and temporary run output stay in
the ignored `.local/` directory.

## Local wiki draft: Design Patterns

### Strategy and Value Objects: rolling-horizon coordination (#61)

- Where: `RollingHorizonStrategy`, `RollingHorizonPlanner`, `FutureVisit`
- Problem: coordinate future holds without exposing or mutating simulator state
- Application: extend the existing Strategy interface with a pure planner and
  frozen visit values; the adapter collects detached audit records and emits
  only one current action
- Rationale: reuse the current registry, pipeline and audit protocol instead of
  creating a second controller or a mutable parallel simulation
- Added in: local issue #61 commit; no PR opened

No external libraries were added, so no Library Comparisons entry is needed.

### Value Objects: downstream forecasts (#62)

- Where: `ProjectedVisit`, `DownstreamCost`, `HorizonAlternative`
- Problem: compare candidate network outcomes without changing the live simulation
- Application: pass frozen forecasts into pure marginal cost evaluation, retaining
  a bounded explanation for each current action in the existing audit collector
- Rationale: copying immutable values avoids a second mutable event engine;
  standard-library topological ordering evaluates the established recurrences
- Added in: local issue #62 commit; no PR opened

## Files by issue

Issue #61 adds `simulator/control/planning.py`, `rolling_horizon.py`,
`strategies/rolling_horizon.py`, and four test/helper files under
`tests/simulator/control/` (`rolling_helpers.py`, `test_rolling_horizon.py`,
`test_rolling_horizon_run.py`, `test_planning_observation.py`). It extends
`decision.py`, `interface.py`, `observation_builder.py`, `prediction_error.py`,
`registry.py`, `settings.py`, `strategies/__init__.py`,
`simulator/trains/train_component.py`, `tests/simulator/test_scenario.py`,
`AI_USAGE.md` and this report. Local commit: `1e8e648`.

Issue #62 adds `simulator/control/downstream.py`,
`tests/simulator/control/test_downstream.py` and `test_downstream_run.py`. It
extends `interface.py`, `observation_builder.py`, `planning.py`,
`rolling_horizon.py`, `strategies/rolling_horizon.py`,
`simulator/trains/train_component.py`, `rolling_helpers.py`,
`test_rolling_horizon.py`, `AI_USAGE.md` and this report.

## Code-quality measurements

Comment percentages count Python comment and docstring lines over nonblank lines
using tokenization and the AST, because `cloc` is not installed.

| Changed source file | Lines | Comments |
|---|---:|---:|
| `simulator/control/decision.py` | 103 | 28.9% |
| `simulator/control/downstream.py` | 234 | 20.6% |
| `simulator/control/interface.py` | 144 | 30.1% |
| `simulator/control/observation_builder.py` | 73 | 21.4% |
| `simulator/control/planning.py` | 71 | 35.7% |
| `simulator/control/prediction_error.py` | 154 | 33.9% |
| `simulator/control/registry.py` | 105 | 21.3% |
| `simulator/control/rolling_horizon.py` | 296 | 20.2% |
| `simulator/control/settings.py` | 248 | 19.8% |
| `simulator/control/strategies/__init__.py` | 24 | 28.6% |
| `simulator/control/strategies/rolling_horizon.py` | 68 | 26.3% |
| `simulator/trains/train_component.py` | 804 | 20.0% |

The new planning models are small type-focused files, where documenting field
semantics produces a higher ratio. Existing commentary in prediction_error.py
was retained. The existing train component's module docstring explains why its
single movement-state owner remains larger than 500 lines. No newly added source
function exceeds 50 lines; pre-existing long movement handlers and operating-rule
parsing remain outside this task's refactoring scope.

Test/helper file line counts and comment ratios: `rolling_helpers.py` 58 / 6.4%,
`test_planning_observation.py` 96 / 2.5%, `test_rolling_horizon.py` 175 / 4.2%,
`test_rolling_horizon_run.py` 119 / 1.8%, `test_downstream.py` 284 / 7.6%,
`test_downstream_run.py` 187 / 1.8%, `tests/simulator/test_scenario.py` 523 / 4.7%.
Tests use descriptive behavior names and comments on hand calculations.

Changed source-line counts (additions, including changed lines): #61 = 494;
#62 = 451. These exceed the normal 400-line PR guideline. The user explicitly
requires exactly one local commit per issue; neither is published as a PR.
Any later review needs at least two reviewers and a team decision on PR splitting.
No remote review or wiki publication was performed.
