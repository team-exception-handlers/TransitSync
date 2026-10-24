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

Each test folder under `run-output` contains `events.jsonl` (one line per event, in processing order), `summary.json` (event counts for the run), and `manifest.json` (scenario metadata and configured disruptions, including whether each delay was applied).

### Disruptions

`DelayInjection` adds a fixed delay to the first matching train arrival at its
selected platform at or after `time_s`. A platform is required; optional
station and train IDs further narrow the target. The delay is configured
independently of its target, contributes to `disruption_delay_s`, and propagates
to later train movements. If no arrival matches during the run, the manifest
records the disruption as unapplied.

```python
from simulator.trains.disruption import DelayInjection
from simulator.trains.train_component import TrainComponent

delay = DelayInjection(
    disruption_id="mcgill-rem-delay",
    time_s=120,
    delay_s=60,
    station_id="mcgill",
    platform_id="STA_ZCD_BT_QUAI_01_MCG",
    train_id="rem-1",
)
component = TrainComponent(trains, delay_injections=(delay,))
```

Named examples are available from `simulator.disruptions`:

```python
from simulator.disruptions import get_disruption_preset
from simulator.trains.train_component import TrainComponent

preset = get_disruption_preset("mcgill_platform_delay")
component = TrainComponent(trains, delay_injections=preset.delay_injections)
```

The available presets are `mcgill_platform_delay`, `green_line_suspension`,
and `uneven_headways`. Each description states the behavior it is intended to
exercise. They use the sample McGill/Green network IDs; adapt their target IDs
when applying them to a different timetable. Set the enclosing scenario's
`name` and `description` to the preset values to identify it in
`manifest.json`. Pass preset suspensions to
`TrainComponent`, or pass `spacing_irregularity_level` to
`generate_from_headway` with the seeded disruptions random stream.

### Code layout

| Path | Contents |
|---|---|
| `simulator/engine/events.py` | Event types, the versioned record schema and the tie order for events at the same time |
| `simulator/engine/event_queue.py` | Event queue and simulation clock |
| `simulator/engine/event_log.py` | Event log, summary and run manifest writers |
| `simulator/engine/runner.py` | Runs one scenario and writes its output |
| `simulator/passengers/corridor.py` | Capacity-limited transfer corridor queue |
| `simulator/passengers/passenger.py` | Passenger identity, station origin/destination and journey state |
| `simulator/passengers/demand.py` | Time-varying demand profiles and expected passenger counts |
| `simulator/passengers/generation.py` | Seeded passenger batches and configurable destination assignment |
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

### Terminal recovery and dispatch perturbations

The train components implement [terminal recovery (#16)](https://github.com/team-exception-handlers/TransitSync/issues/16),
[line suspension (#27)](https://github.com/team-exception-handlers/TransitSync/issues/27)
and [uneven spacing (#28)](https://github.com/team-exception-handlers/TransitSync/issues/28).
They extend the train entity, generators and event handlers from PR #131.
Times and durations below are in seconds. These are Python configuration
interfaces; the scenario file loader, API and frontend are not implemented yet.

**Terminal recovery.** Supply `Train.return_trips` as a tuple of complete,
absolute-time schedules. Each return starts at the previous trip's terminal
station and can use a different platform. The same `Train` object, ID, capacity
and onboard load continue through every trip. For example:

```python
from simulator.trains.train import ScheduledStop, Train

vehicle = Train(
    id="green-vehicle-1",
    capacity=800,
    line_id="green",
    schedule=(
        ScheduledStop("A", "A-out", 0, 0),
        ScheduledStop("B", "B-in", 100, 100),
    ),
    layover_slack=60,
    return_trips=(
        (
            ScheduledStop("B", "B-out", 180, 180),
            ScheduledStop("A", "A-in", 280, 280),
        ),
    ),
)
```

At a terminal arrival, the inbound trip ends. The next actual departure belongs
to the return trip; no extra departure is emitted for the inbound terminal stop.
Following Mathematical Foundations section 6, residual lateness is
`max(0, incoming_delay - layover_slack)`. It is applied once to the return trip,
then ordinary minimum-gap propagation continues. The gap from the inbound
terminal's scheduled departure to the return's first arrival must be positive
and at least the configured slack. The remainder is mandatory turnaround time;
there is no hardcoded operational minimum. In the example, 80 seconds consists
of 60 seconds recoverable slack and 20 seconds mandatory turnaround. An inbound
arrival at 190 (90 late) makes the return ready at 210 (30 late). Any scheduled
inbound terminal dwell is also retained. For delay attribution, recovery reduces
inherited lateness first, then generated lateness. Passenger alighting and
destination selection remain responsibilities of passenger movement logic.

**Line suspension.** Configure immutable `LineSuspension(line_id, start_s, end_s)`
objects on `TrainComponent`. Explicit line IDs are required for every train
when suspensions are configured; generators set these automatically. A suspension
blocks the first departure of every trip on that line during `[start_s, end_s)`.
In-flight trips continue. Dispatch at the end boundary is allowed; overlapping
and adjacent intervals combine. Waiting trains resume in platform arrival order,
with the existing safe gap. Each platform admits only one train at a time;
following arrivals wait until the train occupying it departs. Blocked dispatch
time becomes generated disruption delay and travels downstream, including
through terminal recovery.

An optional `PlatformQueue` queues existing `PassengerArrival` events FIFO on
selected platforms. Attach it to the train component as the sole boarding owner
for those platforms. It boards passengers onto present trains up to available
capacity, emits `Boarding` events, retains overflow for later trains and updates
the final departure's boarding count and load. Passenger arrivals continue during
suspension; passengers can board a train waiting to dispatch, and those without
space remain on the platform. This queue does not generate demand, infer
destinations, apply a door-throughput model or replace future passenger routing.

**Uneven spacing.** Both generators accept keyword-only `irregularity_level`
and `rng`. Zero preserves the original timetable and consumes no random draws.
For a positive level, supply the existing seeded `disruptions` substream:

```python
from simulator.engine.random_streams import StreamManager
from simulator.passengers.platform_queue import PlatformQueue
from simulator.trains.suspension import LineSuspension
from simulator.trains.train_component import TrainComponent
from simulator.trains.train_generator import generate_from_headway

streams = StreamManager(42)
trains = generate_from_headway(
    start_s=0,
    end_s=900,
    headway_s=300,
    route=(ScheduledStop("A", "P", 0, 0), ScheduledStop("B", "Q", 100, 100)),
    capacity=800,
    line_id="green",
    irregularity_level=0.3,
    rng=streams.get_stream("disruptions"),
)
component = TrainComponent(
    trains,
    minimum_gap_s=90,
    suspensions=(LineSuspension("green", 100, 400),),
    passenger_queue=PlatformQueue(("P",)),
)
```

The irregularity level is the headway coefficient of variation: standard
deviation divided by mean. Each interval is multiplied by an independent
positive lognormal draw with mean 1 and variance `level**2`. A 300-second
nominal headway at level 0.3 therefore targets a 90-second standard deviation
and 8100 seconds-squared variance. This distribution and parameter definition
are explicit modelling choices because the issue does not prescribe them.
The first dispatch, vehicle count and route running/dwell durations are retained;
later dispatches can move earlier or later, including beyond the nominal service
window. The resulting times form the requested timetable, rather than additional
delay added again at runtime. For nonuniform input schedules, the variance rule
applies to each interval relative to its own nominal headway.

Operational minimum gaps and suspensions can alter the realised headway
distribution. Tests check the requested distribution separately from these
safety constraints. The runner writes configured delay disruptions and their
applied status to `manifest.json`; event logs remain byte-reproducible.

### Passenger entity and generation

Task #17 provides passenger data and demand-based batch generation. A passenger
has a `passenger_id`, an origin station, a different destination station, and a
`PassengerState`. New passengers start in `CREATED`; the other states are
`WALKING`, `WAITING`, `ON_BOARD` and `COMPLETED`. Passenger snapshots are immutable;
movement components can use `dataclasses.replace` to update their state.

Leading and trailing whitespace is removed from origin and destination station
IDs before they are compared and stored. A destination that becomes the origin,
or duplicates another destination after trimming, is rejected before sampling.

Demand is configured as ordered, non-overlapping time bands. Times are simulation
seconds and rates are passengers per minute. Gaps and times outside the bands
have zero demand. For example:

```python
from simulator.engine.random_streams import StreamManager
from simulator.passengers import DemandPeriod, DemandProfile, PassengerGenerator

demand = DemandProfile(
    (
        DemandPeriod(start_s=0, end_s=60, passengers_per_minute=12),
        DemandPeriod(start_s=60, end_s=120, passengers_per_minute=30),
    )
)
generator = PassengerGenerator(StreamManager(master_seed=42))
passengers = generator.generate(
    origin="mcgill",
    demand_profile=demand,
    start_s=30,
    end_s=90,
    transfer_fractions={"bonaventure": 0.25, "edouard-montpetit": 0.75},
)
```

The expected count in this window is `12 * 30 / 60 + 30 * 30 / 60 = 21`.
Modelling choice: the actual batch size is sampled from a Poisson distribution
with that mean, using the `group_sizes` random stream. Destinations are sampled
from the configured fractions using a separate `destinations` stream. Fractions
describe all modelled destinations and must sum to 1; their mapping order does
not affect the results. A seed and identical call sequence reproduce the complete
passenger batches, including IDs and destinations.

Use one generator per run so passenger IDs remain unique across origins and
batches. If multiple generators are needed, give each a distinct `id_prefix`.
The caller chooses demand windows and must avoid counting the same demand twice.

The numeric ID suffix uses at least 12 digits, for example
`passenger-000000000001`, so IDs with the same prefix still sort in creation
order when the count crosses one million.

This generator returns batches without scheduling platform arrivals. Task #18
will add train-triggered transfer pulses and walking times; task #100 will add
boarding, alighting and missed connections.

## Team

Built by The Exception Handlers, a Concordia University software engineering capstone team.
