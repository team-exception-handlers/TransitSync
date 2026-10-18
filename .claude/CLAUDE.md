# TransitSync

SOEN 490 capstone (Concordia). A decision-support simulator that tests whether holding a Montreal Metro or REM train at an interchange is worth it, so transferring passengers make their connection without costing too much to the people already on board.

Scope is three interchanges only:
- Gare Centrale / Bonaventure (REM ↔ orange line)
- McGill (REM ↔ green line)
- Édouard-Montpetit (REM ↔ blue line)

Buses, real signalling and live deployment are out of scope.

## Repository layout

Target layout. Create folders as they are needed.

```
simulator/   Python discrete-event simulator and control strategies
api/         FastAPI backend (Pydantic validation, runs simulations)
web/         React + TypeScript front end (Zustand, Canvas 2D, Recharts)
config/      Committed config: extracted GTFS values, fitted distributions, scenarios
scripts/     One-time data scripts (load_gtfs.py, GTFS extraction, field data fit)
supabase/    SQL run once in the Supabase SQL editor (gtfs_schema.sql)
.claude/     Claude Code settings and project skills
tests/       pytest + Hypothesis; Playwright for the front end
data/        Local raw GTFS files. Git-ignored, never commit
```

## Stack

- Python 3.12+: NumPy, SciPy, Pandas, pyarrow/Parquet, DuckDB, matplotlib, multiprocessing
- Custom event loop on `heapq`. Do not use SimPy
- Supabase (Postgres) for GTFS tables, user accounts and saved results. Storage bucket `gtfs-raw` holds original feed zips
- GitHub Actions for CI

## Commands

```
py -3.12 -m venv .venv                   # once; project targets Python 3.12+
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest     # all tests
.\.venv\Scripts\python.exe -m ruff check .            # lint
.\.venv\Scripts\python.exe -m ruff format --check .   # format check
python scripts/load_gtfs.py data/rem --agency REM --dry-run
```

Always run Python tools through `.venv`; the system Python (3.14) does not have the project dependencies. `requirements.txt` holds runtime packages, `requirements-dev.txt` adds pytest, Hypothesis and ruff. Update this section as real commands are added.

## Engine core (US-1.1)

- `simulator/engine/events.py` is the frozen event schema. Any change to an event type or field bumps `SCHEMA_VERSION`
- Transferring passengers get one event per passenger (`passenger_id`, plus `group_id` for the transfer burst). Everyone else only appears as counts on `TrainDeparture` (`boarded_count` B, `alighted_count` A, `onboard_load` L)
- `TrainDeparture` is created at the moment the train leaves, never ahead of time, so B, A and L include anyone who boarded during a hold. No hold: the `DepartureDue` handler creates it. Hold: that handler records the `Hold` and schedules a `HoldEnd`, whose handler creates it. The scheduler rejects a `TrainDeparture` not at the current time
- Same-time events follow `EVENT_PRIORITY`, then scheduling order. The scheduler rejects events in the past or earlier in the tie order than the event just processed
- The runner depends on small interfaces in `simulator/engine/runner.py`: `Scenario` (#98), `StreamFactory` (#9) and `ComponentFactory` / `Component` (#97, US-1.2, US-1.3). The stand-ins in `tests/conftest.py` are removed once the real ones are merged
- `run_scenario` rejects an output folder that already has `events.jsonl` or `summary.json`, and a failed run removes everything it wrote
- Output files are byte-reproducible: fixed key order, `\n` line endings, no wall clock time or paths

## Rules for the simulator

These come from the Mathematical Foundations wiki page. Do not break them.

- **Determinism.** Every run is reproducible from one master seed. All randomness comes from `numpy.random.SeedSequence` substreams, one per source: walking times, group sizes, run times, disruptions, loads, prediction errors. Never use `random` or an unseeded generator
- **Common random numbers.** When comparing strategies, each replication uses the same seed for both strategies
- **Pulsed arrivals.** Transferring passengers arrive as a group tied to a train arrival, spread by walking time. Never model them as a constant rate
- **Safety rules live in the simulator, not in strategies.** Maximum hold, minimum gap between trains and the one-hop rule are enforced by the rule checking layer (US-2.5). A strategy only proposes actions
- **Strategies are read-only.** A strategy receives an immutable observation and returns actions. It never touches simulator state
- **No GTFS at runtime.** The simulator reads values from `config/`. GTFS is only read by the one-time extraction script
- **Dwell.** REM uses the fixed scheduled dwell from GTFS. Metro uses `d_min + β_b·B + β_a·A` with swept coefficients
- **Units.** Time in seconds (simulation clock starts at 0). Costs in passenger-seconds
- **Event schema.** Every component writes events in the versioned schema. Changing it needs a schema version bump

## Data

- GTFS tables live in the Supabase `gtfs` schema. Every row has a `feed_id` (e.g. `rem_20260520`). Always filter by `feed_id`
- GTFS times can pass 24:00:00. Use the `arrival_s` / `departure_s` seconds columns, not the text times
- Always apply `calendar_dates` exceptions when picking service for a date
- The REM feed is CC BY 4.0. Anything published needs the credit line from the "Reading GTFS Data" wiki page
- Secrets go in `.env` (git-ignored). Never read `.env` directly, and never print, log or commit `SUPABASE_DB_URL` or any key. `.env.example` lists the names with empty values

## Wiki

- The wiki can be cloned locally at `../TransitSync.wiki`.
- Key pages: Mathematical Foundations, Reading GTFS Data, Security
- Mathematical Foundations is the source of truth for formulas. If code and the page disagree, stop and point out the difference instead of picking one

## Skills

- Project skills: `code-workflow`, `sim-logic`, `gtfs-data`, `python-tests`
- The generic skills (`code-quality`, `testing-strategy`, `performance`, `security-audit`) assume a `src/` layout, `uv` and Python 3.10. In this repo, read `src/` as `simulator/`, `api/` and `scripts/`, install with pip and `requirements*.txt`, and target Python 3.12
- If a skill conflicts with this file, this file wins

## Working with issues

- Work is tracked as GitHub issues: user stories (`US-x.y`) with task sub-issues, plus a few `setup` issues
- GitHub access is read-only. Read issues with `gh issue view <number>` and `gh issue list`, and PRs with `gh pr view <number>`, `gh pr diff <number>` and `gh pr list`. Never commit, push, open PRs, or create, edit or comment on issues. The team does all of that
- Before starting a task, read the issue and its parent user story
- Stay inside the task's scope. If something else needs changing, say so at the end instead of doing it
- When a task is done, suggest a commit message in the present tense that references the issue, e.g. `Add event queue and clock (#42)`
- Every feature or fix PR fills the AI declaration in `.github/pull_request_template.md`: the level for the code the PR changes and the list of AI-assisted files. Draft the matching row (and, for at least half of features, a development example) for `AI_USAGE.md`. File headers, the PR declaration and `AI_USAGE.md` must agree

## Tests

- Every task adds or updates tests
- Simulator logic gets unit tests with hand-calculated expected values
- Use Hypothesis for properties that must always hold (minimum gap never violated, holds never exceed the cap, same seed gives same output)
- The determinism test must pass in CI

## Writing style for docs, issues and wiki pages

- Define transit and math terms the first time they appear, at a first-year level
- No trailing periods on bullet items in task issues
- Task issue format:

```
### [TASK] <title>
**Priority:** <1-3> · **Risk:** <Low/Medium/High> · **Related to:** US-x.y
**Description:** <one sentence>
**Breakdown:**
- <step>
```
