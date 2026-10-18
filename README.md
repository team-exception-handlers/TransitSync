# TransitSync

**A smarter way to think about connections between Montréal's Metro and REM.**

When we miss a connection, it can add a lot of time to our trip. If we decide holding a Metro train for arriving passengers, it would also delay everyone already on board and can affect the trains behind it. Our capstone project explores how to make that tradeoff more thoughtfully.

TransitSync is a **simulation and decision-support prototype** for coordinating transfers between the STM Metro and the REM. It tests whether a short train hold could help more passengers than it delays. The aim is to give transit planners a way to compare possible strategies and choose the best one in different situations.

## What we're building

- A simulation of passenger transfers and train movement, starting with Metro–REM connections.
- A controller that considers arriving passengers, passengers already on board, and the effect of a delay farther along the line.
- A maximum hold time.
- A comparison of trips with and without the controller, using different measures such as missed connections, passenger waiting time, and total passenger delay.
- A way to visualize decisions and results so we can explain *why or why not* the controller chose to hold or release a train.

We plan to begin with Metro–REM transfers, then explore transfers between Metro lines i time allows us to do so.

## A simple example

Suppose a REM train is arriving and several passengers are about to transfer to the Metro. Should the Metro wait few seconds extra so the passengers coming can make it and not wait an at least extra 5 minutes? TransitSync estimates how much time those passengers might save and weighs that against the delay to people on the Metro and people waiting farther down the line. Sometimes waiting will make sense; sometimes letting the train leave will be better for the network as a whole.

## Project status

This is a 1 year software engineering capstone project at Concordia University, built by The Exception Handlers team.

## Getting started

The simulation engine core (event schema, event queue and clock, simulation runner) is in place and covered by tests. There is no user interface or command-line program yet; a run is started from Python or from the tests.

### Requirements

- Python 3.12 or newer (`py --list` shows the installed versions on Windows)
- Git

### Setup

```powershell
git clone https://github.com/Gur-Lal/TransitSync.git
cd TransitSync
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
```

On macOS or Linux, the environment is created with `python3.12 -m venv .venv` and activated with `source .venv/bin/activate`.

If PowerShell blocks `Activate.ps1`, running `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once allows it. In VS Code, the interpreter is set to `.venv\Scripts\python.exe` through **Python: Select Interpreter**.

### Running the checks

```powershell
pytest -v                 # all tests, one line per test
ruff check .              # lint, including the complexity and function size limits
ruff format --check .     # formatting
```

### Seeing a simulation run

The smoke test runs a small timetable at McGill (one REM train, two green line trains) and writes the run output. Keeping the output folder shows the files a run produces:

```powershell
pytest tests/simulator/engine/test_runner.py --basetemp=run-output
```

Each test folder under `run-output` contains `events.jsonl` (one line per event, in processing order) and `summary.json` (event counts for the run).

### Code layout

| Path | Contents |
|---|---|
| `simulator/engine/events.py` | Event types, the versioned record schema and the tie order for events at the same time |
| `simulator/engine/event_queue.py` | Event queue and simulation clock |
| `simulator/engine/event_log.py` | Event log writer and run summary |
| `simulator/engine/runner.py` | Runs one scenario and writes its output |
| `simulator/passengers/corridor.py` | Capacity-limited transfer corridor queue |
| `tests/` | pytest and Hypothesis tests, mirroring the source tree |

The developer guide on the wiki ("Engine Core Developer Guide") explains how the US-1.1 tasks plug into the runner.

### Passenger event recording

By default, `run_scenario` records every processed event in `events.jsonl`.
Each passenger record includes `passenger_id`, `time_s` (seconds) and
`schema_version`. Selecting records for one passenger preserves their timeline
order, including events with the same timestamp. The passenger components are
responsible for emitting alighting, platform arrival, boarding and missed
connection events as those transitions happen.

For sweep runs, pass the passenger event types to the optional log filter:

```python
from simulator.engine.event_log import PASSENGER_EVENT_TYPES
from simulator.engine.runner import run_scenario

# Uses the same scenario, factories and output directory as a regular run.
result = run_scenario(
    scenario,
    build_streams,
    build_components,
    output_dir,
    skip_event_types=PASSENGER_EVENT_TYPES,
)
```

`skip_event_types` accepts a set or frozenset of `EventType` members. Omitting
it, or passing an empty set, logs everything. Filtering only affects the event
log: components still process every event, and `summary.json` still counts all
events. The summary's sorted `skipped_event_types` list records which event
types were omitted, and is empty for a full log. A filtered log cannot
reconstruct the omitted passenger timelines.

### Transfer corridor queueing

`CorridorQueue` limits passage through a transfer corridor to a configured
number of passengers per minute. Passengers are admitted first-in, first-out
into evenly spaced slots of `60 / capacity_per_minute` seconds. A passenger
arriving after the queue clears passes immediately; unused capacity is not
saved for a later burst.

Calling `admit(passenger_id, arrival_s)` returns the passenger's bottleneck
arrival time, actual passage time and queueing delay, all in seconds. Passenger
generation and walking-time sampling can therefore supply arrival times without
the corridor depending on their unfinished implementations.

## Team

Built by The Exception Handlers, a Concordia University software engineering capstone team.
