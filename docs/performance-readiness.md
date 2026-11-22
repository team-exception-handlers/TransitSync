# Performance task readiness

**The complete assignment is not ready to merge.** The strict performance
checks still fail. This audit integrates main `e5e0b6a` into the performance
branch and preserves the other developers' passenger outcomes, comparisons,
charts, operating-rule response and parameter provenance changes. No PR was
opened. Historical measurements remain in `performance.md`; the observations
here supersede its earlier statement that no comparison endpoint exists.

## Acceptance audit

| Task | Implemented and verified | Remaining acceptance gap |
|---|---|---|
| Performance tests and baseline | All six registered strategies; 30 strict checks; default marker exclusion; printed timings; fixed settings; uncached requests; separate profiling | Several targets fail; browser display time is not certified by backend bounds |
| One-hour request-to-response profiling | Simulation, log processing, passenger tracks, adapter and serialization profiled; focused optimizations; byte-equivalence and seeded log tests | No completed default Coordinated request, so its full response has not been certified |
| Coordinated execution | Prepared projections, costs, fixed candidate positions and reusable grid decisions; original seeded decisions/audits and captured production-plan digest retained | Production request and comparison remain too slow; full paired-run endpoint is still in unmerged PR #409 |
| Full-day execution | Scenario.duration_s set directly to 92,576 s; one-hour production default preserved; five completed strategies below 30 s in the independent suite | Coordinated did not finish; full-day results preparation still exceeds 2 s |

The startup and parameter checks time an entire uncached synchronous HTTP
response, a necessary backend bound before playback can display. Results time
starts after the simulator returns. These bounds do not include browser
transport, JSON parsing or drawing. Targets and search budgets were not relaxed.

## Additional fixes

- Resolve shared-file merge conflicts by retaining both main's features and the performance readers
- Retain small explicit timeline hold records while consuming the estimate stream once; this preserves the new chart's second audit consumer without retaining full-network estimate dictionaries
- Batch concrete NumPy generator draws without changing their sequence, Python-float arithmetic, custom-stream fallback or dataclass-subclass behavior
- Reuse fixed projection positions and grid decisions inside each immutable planning observation; preserve candidate order, counts and arithmetic order
- Add an explicit benchmark for the passenger-comparison endpoint, recording its actual endpoint and individual simulator durations

## Independent timing suite

Command:

```powershell
python -m pytest tests/performance -m performance -q -s --performance-timeout=45
```

Result: **13 passed, 13 failed, four setup errors in 322.40 s**. The four
setup errors are two unfinished Coordinated fixtures, each serving two checks.
The Coordinated parameter experiment also times out. Other failures are strict
latency assertions, not simulator exceptions. The worker budget includes
process startup; returned API timings exclude it. A timeout has no known
completion time and is never substituted as a measured duration.

| Strategy | Startup (s; target 2) | Parameters (s; target 1) | Hour results (s; target 2) | Full day (s; target 30) | Day results (s; target 2) |
|---|---:|---:|---:|---:|---:|
| adaptive | 2.059 | 2.077 | 0.263 | 28.068 | 4.322 |
| connection_protection | 2.045 | 2.046 | 0.271 | 28.035 | 4.201 |
| headway_regulation | 1.994 | 2.022 | 0.250 | 27.508 | 4.273 |
| no_control | 1.977 | 2.082 | 0.251 | 26.969 | 4.286 |
| schedule_based | 1.997 | 2.003 | 0.244 | 26.347 | 4.036 |
| rolling_horizon | Unfinished | Unfinished | Unfinished | Unfinished | Unfinished |

These are individual independent samples, not medians. Retain slow observations
and apply the limits literally: startup values near 2 s are not a robust browser
pass. The raw sample file records full precision, settings, response fingerprints
and scenario data.

Measured production sources correspond to commit `70a8f8c`; benchmark helper
updates were still uncommitted during collection and are included in this
branch. The integrated reference is `f8eb2c4`. Generated artifacts stay ignored;
the raw report distinguishes timed experiments from concurrent correctness runs.

## Regression and quality checks

- Python CI-equivalent coverage run: **1,849 passed, 30 performance checks deselected, one existing expected failure** in 205.73 s
- Frontend coverage run: **396 passed** across 34 files; 95.19% statements and 96.17% lines
- Frontend typecheck and lint: passed
- Standard Ruff, formatting and extended rules on changed Python files: passed
- All 15 completed independent simulation responses, plus the completed comparison response, match the integrated reference fingerprints exactly
- Seeded Coordinated decision/audit regressions and the captured production-plan digest: unchanged

Fingerprint-only reference runs were performed alongside CI; their execution
times are deliberately excluded from performance comparisons. The complete
Coordinated production request did not finish, so it has no full-run output
equivalence claim. Local checks do not substitute for the future PR's remote
quality scan.

## Before-and-after evidence

Single integrated pre-optimization No-control samples took 2.234 s for an hourly
request and 30.138 s for a full-day request (25.989 s simulation, 4.129 s results).
The independent optimized observations above took 1.977 s and 26.969 s. Completed
responses retain their original fingerprints for the integrated schema.

Five additional uncontended No-control hourly requests had median 1.934 s and
range 1.892-1.966 s. The separate profiled request took 3.467 s, 1.793 times the
unprofiled median. Profiling remains separate from latency assertions.

Three additional sequential No-control full-day requests took 26.199, 26.873
and 27.055 s (median 26.873 s), all retaining the reference full response digest.
Their results phases took 4.027, 4.072 and 4.214 s: the separate results target
still fails even though those full requests are below 30 s.

The captured Coordinated decision has the same complete plan SHA-256
`256884d677f2749fcf917d1410c126f91366def382b75cc3b2fe42a9e789fba8`
and 41,401 evaluations in all five additional runs: 1.841-1.907 s,
median 1.857 s. The earlier implementation on this branch had median 2.332 s;
the original unoptimized reference had median 22.272 s. This is one planning
observation, not a complete simulation or comparison request.

An extended integrated pre-optimization Coordinated request still had no response
when stopped after 545.957 s of observed worker time, beyond its 500 s experiment
budget. No completion time or full response digest exists for that experiment.

## Comparison endpoints and parallel work

Current main provides `/simulation/passenger-comparison`. A fixed-seed functional
fixture executes real Coordinated planning through that route, then verifies
both returned outcome lists against their cached station-view responses. The
fixture uses a 60-second scenario and a 10-second hold limit to keep ordinary CI
fast; production performance measurements keep the one-hour/default-300-second
settings. The fixture is not a performance acceptance result.

An uncached production Coordinated passenger-comparison experiment remained
unfinished within a 120 s worker budget. No completed comparison response or
completion time is claimed. Three completed connection-protection comparison
requests took 3.886, 3.923 and 3.979 s (median 3.923 s), with identical response
digests and both simulator durations recorded. These are observations, not an
invented acceptance threshold for comparison.

The full paired station-view endpoint `/simulation/comparison` is in open
[PR #409](https://github.com/team-exception-handlers/TransitSync/pull/409).
It runs the selected strategy and No-control through the same service. Current
main's passenger-outcome endpoint is a different response contract. Do not
present its benchmark as certification of the pending paired endpoint.

Other shared-file risks reviewed:

- [PR #406](https://github.com/team-exception-handlers/TransitSync/pull/406) changes prediction errors to keyed draws. Preserve that intended behavior when resolving the future merge; sequential draw batching is not an implementation of keyed randomness. Re-establish reference outputs from the upstream implementation before reapplying optimizations
- [PR #410](https://github.com/team-exception-handlers/TransitSync/pull/410) adds cached results and touches the service and station-view response. Recheck response equivalence after integration

## Reproduce the additional measurements

Run from the repository root using the existing Python environment:

```powershell
python -m pytest -q --cov --cov-report=xml
python -m pytest tests/api/test_performance_integration.py -q
python -m scripts.benchmark_simulation --strategy no_control --full-day --repeats 3 --output .benchmarks/day-check
python -m scripts.benchmark_simulation --strategy connection_protection --compare --repeats 3 --output .benchmarks/comparison-check
python -m scripts.benchmark_simulation --strategy rolling_horizon --compare --repeats 1 --output .benchmarks/coordinated-comparison
```

The CLI has no deadline; Coordinated can run for many minutes. The `--compare`
flag currently selects `/simulation/passenger-comparison`. It sums simulator
durations from both subruns; results_s covers only preparation after the final
simulation returns. Total request_s includes both complete adaptations and HTTP
serialization. With `--capture`, the response is the full comparison but the
captured log files belong to its final simulator subrun. Changed-parameter
benchmarks use `/simulation/run`; combining `--changed` with `--compare` is
rejected because comparison normalizes baseline control-only parameters.

## Review and merge requirements

The complete source diff is 778 added/changed source lines, exceeding the
repository's 400-line PR cap. The prepared review patches have these sizes:

| Unit | Source lines | Minimum reviewers |
|---|---:|---:|
| Benchmark tools and tests | 287 | 2 |
| Encoded decision audits | 103 | 1 |
| Coordinated forecasts | 223 | 1 |
| Full-day response preparation | 165 | 1 |
| Measurement reports | 0 | 1 |

Separate commits preserve the intended four review units: benchmark tools/tests,
encoded audit storage, Coordinated scoring, and full-day response preparation.
Keep the measurements as a separate documentation commit. Tests and documents
do not count toward that source cap. Split the eventual PRs using these units;
commits alone do not make an oversized single PR compliant.

Before marking the complete assignment ready:

1. Reduce and remeasure production Coordinated execution and its full paired comparison without changing decisions, budgets or audit output
2. Meet the 1 s uncached parameter bound, both remaining startup failures, and the 2 s full-day results bound
3. Complete all six full-day checks and repeat representative measurements for variability
4. Integrate or test the final paired-comparison interface once PR #409 lands, then measure browser click-to-display latency
5. Run the resulting PR's quality scan and review its source size; no remote PR scan has been triggered here

AI contribution: 50% or more AI-generated, Codex (OpenAI). All measurements are
actual observations; incomplete experiments remain explicitly incomplete.

Schedule data from the Réseau express métropolitain (REM), [rem.info](https://rem.info),
used under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
Data has been processed and modified for this project.
