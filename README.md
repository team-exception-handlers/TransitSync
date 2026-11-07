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

The simulation engine core (event schema, event queue and clock, simulation runner) is in place and covered by tests. The backend provides a health check and a station-layout endpoint, but does not yet expose simulation runs. The frontend is a mock playback interface and does not yet retrieve simulation data from the backend. Simulation runs are started from Python or from the tests.

### Requirements

- Docker Desktop for Windows with Docker Compose
- Git

Python and Node.js are not required to run the application with Docker. Docker
downloads the base images and installs the pinned project dependencies during
the first build.

### Build and run with Docker (recommended)

```powershell
git clone https://github.com/Gur-Lal/TransitSync.git
cd TransitSync
docker compose up --build
```

When the services start, open:

- Frontend: <http://localhost:5173>
- Backend health check: <http://localhost:8000/health>
- Backend McGill layout: <http://localhost:8000/station-layout/mcgill>
- Backend API documentation: <http://localhost:8000/docs>

The backend permits the frontend origin `http://localhost:5173` by default.
To allow additional browser origins, set `TRANSITSYNC_CORS_ORIGINS` to a
comma-separated list of exact HTTP(S) origins in PowerShell before starting
Compose:

```powershell
$env:TRANSITSYNC_CORS_ORIGINS = "http://localhost:5173,http://127.0.0.1:5173"
docker compose up --build
```

Press `Ctrl+C` to stop services running in the foreground. To run them in the
background instead, use `docker compose up --build --detach`; stop and remove
the containers and network with `docker compose down`.

If Docker Desktop's integrated builder fails with `exec format error`, try a
separate BuildKit builder:

```powershell
docker buildx create --name transitsync-builder --driver docker-container
docker compose build --builder transitsync-builder
docker compose up --detach
```

### Local development (optional)

For running the Python tests or developing without containers, install Python
3.12 or newer and Node.js 22.22.2 or newer. From the repository root, create a
Python virtual environment and install the development dependencies:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
```

On macOS or Linux, create the environment with `python3.12 -m venv .venv` and
activate it with `source .venv/bin/activate`. In VS Code, select
`.venv\Scripts\python.exe` through **Python: Select Interpreter** on Windows.

Install the frontend dependencies from the lockfile with `npm ci` in `web/`.
Run the frontend with `npm run dev` from that directory and the API in a
separate terminal from the repository root:

```powershell
$env:TRANSITSYNC_CORS_ORIGINS = "http://localhost:5173"
python -m uvicorn api.main:app --reload
```

The `.venv` and `web/node_modules` directories are local development artifacts;
they are excluded from Docker build contexts.

### Running the checks

```powershell
pytest -v                     # all tests, one line per test
ruff check .                  # lint, including complexity and function size limits
ruff format --check .         # formatting
docker compose config         # validate the container configuration
```

### API behavior

The backend exposes `GET /health` and `GET /station-layout/{interchange_id}`.
The station-layout endpoint returns platforms, their map coordinates, station
markers, connection records, and transfer corridor paths for
`gare_centrale_bonaventure`, `mcgill`, or `edouard_montpetit`. The current
coordinates are schematic: the front end's McGill fixture geometry is reused
for all three interchanges. The Gare Centrale–Bonaventure and
Édouard-Montpetit entries are placeholders; replace their geometry in
`config/station_layouts.json` when real layouts are prepared. Platform metadata
comes from the reference network; the layout catalog stores only map-specific
platform positions and transfer geometry. The endpoint does not include
passenger or train playback data.

The default allowed browser origin is `http://localhost:5173`. Configure
additional exact HTTP(S) origins through
the `TRANSITSYNC_CORS_ORIGINS` environment variable; invalid values are rejected
when the API starts. The API reads settings from its process environment, not
from committed files. The health endpoint is available at
<http://localhost:8000/health> when running with Docker.

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
    platform_id="rem_mcgill_0",
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
| `api/main.py` | FastAPI application factory, health, and station-layout endpoints |
| `api/settings.py` | Environment-backed API settings and CORS origin validation |
| `api/station_layout.py` | Validated map geometry and platform mapping |
| `config/station_layouts.json` | Map-ready station layouts for the three interchanges |
| `simulator/engine/events.py` | Event types, the versioned record schema and the tie order for events at the same time |
| `simulator/engine/event_queue.py` | Event queue and simulation clock |
| `simulator/engine/event_log.py` | Event log, summary and run manifest writers |
| `simulator/engine/runner.py` | Runs one scenario and writes its output |
| `simulator/network_config.py` | Reads and checks the saved network and train schedules |
| `simulator/network.py` | Groups platforms by station and line, and finds transfer connections |
| `simulator/passengers/corridor.py` | Capacity-limited transfer corridor queue |
| `simulator/passengers/passenger.py` | Passenger identity, station origin/destination and journey state |
| `simulator/passengers/demand.py` | Time-varying demand profiles and expected passenger counts |
| `simulator/passengers/generation.py` | Seeded passenger batches and configurable destination assignment |
| `simulator/passengers/transfer_component.py` | Train-triggered transfer groups, walking times and corridor arrivals |
| `simulator/passengers/platform_queue.py` | FIFO boarding, destination alighting, onboard identities and missed connections |
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

Holding delay is tracked separately from disruption delay. The hold record keeps
all time spent waiting, even when the train is early: a train held for 30 seconds
while 10 seconds early gains only 20 seconds of lateness. This distinction stays
with the train at later stops. Recovery first removes delay inherited from other
trains, then reduces its own holding and disruption delays in proportion.

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

Overlapping holds and suspensions are not counted twice. If a train is ready at
280 seconds, held until 400, but already blocked until 450, the hold adds no extra
lateness. If the blockage ends at 350, only the extra 50 seconds count as holding
delay. A blockage caused by staying for a hold counts towards that hold's delay.

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

### Train capacity and left-behind passengers (#24)

`Train.capacity` is an explicit whole-passenger limit, including seated and
standing riders. Initial load must be an integer between zero and capacity.
Python and NumPy integers are accepted and normalized before arithmetic;
booleans and fractional counts are rejected.

The existing `PlatformQueue` boards compatible destinations in arrival order,
up to remaining capacity. Skipped destinations and overflow passengers stay in
their original queue order for later trains; callers must not enqueue them again.
Tracked passengers remain `WAITING` until they board. A missed-connection record
does not remove them. Destination alighting frees space before boarding, and
untracked initial riders continue to occupy capacity.

Capacity research for scenario authors (whole train, not seats; researched
2026-11-06):

| Rolling stock | Published capacity | Interpretation and source |
|---|---:|---|
| REM, four cars | 600 | Theoretical capacity in the operator's [rolling-stock specification](https://rem.info/en/rolling-stock). |
| REM, four cars | 780 | Maximum comparison figure in the operator's [capacity explanation](https://rem.info/en/news/rem-seating-and-capacity), rather than the theoretical 600. |
| AZUR, nine cars | 1,104 | W3 loading figure from STM's [technical sheet](https://www.stm.info/sites/default/files/feuillet_azur-web_ang.pdf). Search-indexed sheet; direct retrieval returned 404 during research. Reconfirm the document before using it for calibrated scenarios. |
| MR-73 | 160 per car | Historical total-capacity entry in [TCRP Report 13, Table A3.5](https://onlinepubs.trb.org/onlinepubs/tcrp/tcrp_rpt_13.pdf). Multiplying by a scenario's six or nine cars gives 960 or 1,440; these are derived historical assumptions, not verified current operating limits. |

Choose and record the actual stock, formation, source, and loading assumption
when constructing trains. Do not infer stock or formation from a line or GTFS
trip. No universal capacity default is introduced. Test fixtures deliberately
use small capacities; they are not estimates of real trains.

REM door throughput follows the aggregate fixed-window budget in
[Mathematical Foundations, section 4](https://github.com/team-exception-handlers/TransitSync/wiki/Mathematical-Foundations#4-dwell-time-and-boarding-capacity)
via explicit per-train configuration:

```python
from simulator.trains.door_throughput import DoorThroughput

# Illustrative only: replace with measured or documented scenario parameters.
component = TrainComponent(
    trains,
    passenger_queue=queue,
    rem_door_throughput={"rem-train-id": DoorThroughput(0.2, 2)},
)
```

Each configured train gets `floor(rate * scheduled_dwell_seconds * doors)`
boardings per stop, additionally bounded by remaining vehicle capacity. Repeated
arrivals share the budget; passengers who cannot board retain their queue order
and `WAITING` state. Each new visit starts a fresh budget. Unknown train IDs and
invalid rates or door counts are rejected. The run manifest records the settings.

Following section 4's scheduled-dwell formula, holds and dispatch waits allow
later arrivals to use an unspent budget but do not enlarge or reset it. Scheduled
REM dwell remains unchanged. This is an aggregate stop budget, not continuous
per-passenger door-service timing. Metro and other unlisted trains keep their
existing boarding behaviour. No REM identity or measured rate is inferred:
scenario builders must supply this configuration for REM runs; unconfigured
trains enforce vehicle capacity only.

The [LLL prototype PR #186](https://github.com/team-exception-handlers/TransitSync/pull/186)
supplies the original stateful checks. The #24 tests extend its independent FIFO
reference model to tracked passengers, different destinations and later trains.
Existing scheduler integration tests cover full departures and later recovery.

### Dwell time model

`simulator.trains.dwell.DwellModel` computes demand-dependent **Metro** dwell in
seconds, following [Mathematical Foundations, section 4](https://github.com/team-exception-handlers/TransitSync/wiki/Mathematical-Foundations#4-dwell-time-and-boarding-capacity).
Use it only for Metro trains. **REM dwell stays fixed at the scheduled value**
because REM doors close on a timer. Setting crowding strength to zero alone is
not enough for REM: the boarding/alighting terms would still vary its dwell.
The caller must select the model by network; `DwellModel` has no network identity.

```python
from simulator.trains.dwell import DwellModel

# Illustrative coefficients only; supply calibrated values for a real scenario.
model = DwellModel(
    base_dwell_s=20.0,
    boarding_s_per_passenger=1.5,
    alighting_s_per_passenger=0.75,
)
assert model.compute(boarded_count=10, alighted_count=8) == 41.0
```

The example is hand-calculated as `20 + 1.5 * 10 + 0.75 * 8 = 41` seconds.
The counts are passengers who actually board or alight at this stop; passengers
left on the platform do not contribute to the boarding count.

Run the focused checks with:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/simulator/trains/test_dwell.py -v
```

Tests cover zero passenger movements, each flow separately, mixed flows,
increasing counts, disabled terms, invalid inputs and arithmetic overflow.

The formula is `base + boarding_coefficient * B + alighting_coefficient * A`.
This additive approximation treats boarding and alighting as sequential service;
coefficients describe effective throughput across the train. They are required
configuration inputs, with no assumed calibrated defaults. All coefficients must
be finite and non-negative; counts must be non-negative integers. With no
passenger movements, dwell equals the base. A zero coefficient disables its term.

[Task #22](https://github.com/team-exception-handlers/TransitSync/issues/22)
supplies this standalone calculation and hand-calculated tests in
[PR #136](https://github.com/team-exception-handlers/TransitSync/pull/136).
`TrainComponent` uses scheduled dwell, extended by configured holds and dispatch
constraints. Task #100 records live boarding/alighting counts in departures;
rescheduling dwell from `DwellModel` coefficients remains separate integration work.

[Task #23](https://github.com/team-exception-handlers/TransitSync/issues/23) adds
optional crowding in
[PR #179](https://github.com/team-exception-handlers/TransitSync/pull/179):

```python
model = DwellModel(20.0, 1.5, 0.75, crowding_strength=2.0)
assert (
    model.compute(boarded_count=10, alighted_count=8, onboard_load=50, capacity=100)
    == 43.625
)
```

Let `service = boarding_coefficient * B + alighting_coefficient * A` and
`r = max(arrival_load, onboard_load) / capacity`. Dwell is
`base + service + service * crowding_strength * r**crowding_exponent`.
Supply final `onboard_load` **after alighting and boarding**, excluding passengers
left behind. The model infers `arrival_load = onboard_load - B + A`, assuming
alighting precedes boarding. Using the peak of arrival and final load keeps a
crowding penalty when a train arrives packed and many passengers get off.
For the example, service is 21 seconds and the extra delay is
`21 * 2 * 0.5**4 = 2.625` seconds. At full capacity dwell is 83 seconds.
For example, with base 20, alighting coefficient 1 and strength 1, a train that
arrives full at capacity 1000 and drops off 500 passengers has 1020 seconds of
dwell: `20 + 500 + 500 * 1**4`. Using only its final load would give 551.25 seconds.

The default quartic curve gives progressively steeper increases near capacity
and has no singularity at full load. Set `crowding_exponent` (default `4.0`) to
any finite value greater than one for sensitivity analysis, such as 2, 3 or 4.
Strength and exponent are modeling choices requiring calibration, rather than
measured transit relationships. Strength is dimensionless and non-negative;
at full load it specifies the extra fraction of passenger service time.
The default strength of zero preserves the original model and allows omitted
load/capacity. Enabled crowding requires both: integer load between zero and
capacity, and positive integer capacity. Supplied load/capacity are validated
even when crowding is disabled. Passenger counts must be consistent with the
supplied loads: boarded passengers cannot exceed final load and inferred arrival
load cannot exceed capacity. Real numeric coefficients, including NumPy scalars,
are normalized to Python floats. Zero passenger service still returns base dwell.
Non-finite computed dwell is rejected with `ValueError`.
Dynamic departure scheduling remains separate integration work.

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
connects it to train arrivals, walking times and corridor queues as described below.
Task #100 connects those arrivals to destination-aware boarding and alighting.

### Pulsed transfer arrivals

`TransferComponent` creates a complete passenger group when a feeder train
actually arrives at a configured station and platform. Each passenger then walks
for an independently sampled duration. Passengers enter the corridor queue in
the order they reach it, including when groups from different trains overlap.
Their `PassengerArrival` event marks reaching the connecting platform after
walking and corridor queueing. With no feeder train, no passengers are generated.

Build the component inside the runner's component factory, using the supplied
seeded streams. This example uses illustrative demand, walking and capacity
values; choose appropriate values for the scenario:

```python
from simulator.passengers import (
    CorridorQueue,
    DemandPeriod,
    DemandProfile,
    TransferComponent,
    TransferRoute,
)
from simulator.passengers.platform_queue import PlatformQueue
from simulator.trains.train import ScheduledStop, Train
from simulator.trains.train_component import TrainComponent


def build_components(scenario, streams):
    trains = [
        Train("feeder", 800, (ScheduledStop("mcgill", "rem_mcgill_0", 120, 150),)),
        Train(
            "connecting",
            800,
            (
                ScheduledStop("mcgill", "green_mcgill_1", 240, 270),
                ScheduledStop("next-station", "next-platform", 360, 390),
            ),
        ),
    ]
    transfers = TransferComponent(
        [
            TransferRoute(
                station_id="mcgill",
                feeder_platform_id="rem_mcgill_0",
                connecting_platform_id="green_mcgill_1",
                demand_profile=DemandProfile((DemandPeriod(0, 3600, 12),)),
                transfer_fractions={"next-station": 1.0},
                corridor=CorridorQueue(capacity_per_minute=60),
                walking_mean_s=120,
                walking_min_s=30,
            )
        ],
        streams,
    )
    return [
        TrainComponent(
            trains,
            passenger_queue=PlatformQueue(
                ("green_mcgill_1",), passengers=transfers.passengers
            ),
        ),
        transfers,
    ]
```

Replace `next-station` with the actual destination station ID. The demand rate
is passengers per minute; all event times and walking durations are seconds.
Demand accumulates from `demand_start_s` (default 0) to the first actual feeder
arrival, then between successive arrivals on that route. A train arriving at
the demand start produces no passengers for the empty interval. This demand
represents external feeder transfers and is not deducted from aggregate feeder
train loads. Walking uses the existing seeded `WalkingTimeSampler` distribution.

Use one route per station/feeder-platform pair. Routes sharing a physical corridor
must share the same `CorridorQueue` instance. Construct fresh components and
queues for each run. The existing `PlatformQueue` remains the sole boarding owner
on its platforms. With the shared passenger dictionary attached, it tracks
destinations, boarding, completed journeys and missed connections as described below.

Event schema version 4 adds `CorridorArrival` between alighting and platform
arrival in the event tie order. The passenger log filter automatically includes
this event. Logs written with older schema versions must be regenerated.

Run the focused tests on macOS with:

```sh
.venv/bin/python -m pytest tests/simulator/passengers/test_transfer_component.py -v
```

### Boarding, alighting and missed connections

Task #100 extends the existing `PlatformQueue`. Pass the same passenger dictionary
used by `TransferComponent` through `PlatformQueue(..., passengers=transfers.passengers)`.
Attach the queue to `TrainComponent`; it does all event handling for the queue,
so no second boarding component is needed. The example above uses this wiring.

Passengers board in platform arrival order while the train is present, including
during holds, line suspensions and minimum-gap departure waits. Available seats
limit boarding. A passenger whose destination is absent from the train's remaining
trip stays queued and does not block compatible passengers behind them. Arrivals
at exactly the actual departure time can board because passenger arrivals and
boarding sort before departure in the event queue.

At each arrival, tracked passengers whose destination matches the station alight
and become `COMPLETED`. Their seats are freed before waiting passengers board.
This also works at a terminus before the vehicle starts its return trip. Departure
records contain final boarding/alighting counts and onboard load for that stop.
The existing controller observations read the same queue and live train loads.

A compatible passenger left waiting when a train departs gets a `MissedConnection`
record. A passenger reaching the platform later gets a miss for the first compatible
departure since their feeder alighting. Each passenger's transfer gets at most one
miss, even if more full trains leave them behind. Trains that left before the
transfer began are excluded. A missed passenger stays waiting and can board a later
train; the record does not mark their journey completed.

For passengers already onboard at run start, supply `initial_onboard`, mapping
train IDs to passenger ID sequences. Each listed passenger must be `ON_BOARD`,
have a reachable destination and already be included in that train's initial
`onboard_load`. All initial `ON_BOARD` passengers must be listed exactly once.
Untracked aggregate passengers retain their seats. Newly generated feeder
transfers count as external alightings without subtracting that load again.

Without a passenger dictionary, `PlatformQueue` retains capacity-only FIFO
boarding for existing callers. Times are simulation seconds. Passenger movements
use the current door-open window; calibrated door throughput and dynamic dwell
rescheduling are not introduced by this task. No event schema change is required.

Run the focused macOS checks with:

```sh
.venv/bin/python -m pytest tests/simulator/passengers/test_boarding.py tests/simulator/passengers/test_boarding_validation.py -v
```

### Network model

The network model groups saved platforms by station and line, with one shared
transfer corridor connecting REM and Metro platforms at each interchange.

```python
from pathlib import Path

from simulator.network import build_network
from simulator.network_config import load_network

network = build_network(load_network(Path("config/reference_network/network.json")))
corridor = network.corridor_for("rem_mcgill_0", "green_mcgill_1")
```

`corridor_for` returns the same corridor for transfers in either direction,
`None` for known platforms without a link, and raises `KeyError` for unknown IDs.

The model is read-only. Train and passenger movement, queues and walking times
are handled by runtime components.

### Schedule-based holding

Schedule-based holding (`schedule_based`) makes an early train wait until its
scheduled departure. For example, a train ready to leave 10 seconds early waits
those 10 seconds. A train that is on time or late receives no extra hold.

With no control (`no_control`), a train can leave as soon as it completes its
normal stop, even if early. Both options follow operating restrictions, which
can delay departure further. Passengers can board while a train is held.
Passenger numbers and transfers do not determine whether these policies hold.

The Python example below runs the same train under each policy. Use an already
loaded `scenario` lasting at least 230 seconds; both runs keep the same timetable
and random seed:

```python
from dataclasses import replace
from pathlib import Path

from simulator.control.decision import DecisionPipeline
from simulator.control.settings import parse_control_settings
from simulator.control.strategies import STRATEGIES
from simulator.engine.random_streams import StreamManager
from simulator.engine.runner import run_scenario
from simulator.trains.train import ScheduledStop, Train
from simulator.trains.train_component import TrainComponent


def build_components(settings, _streams):
    """Create fresh trains and the selected controller for each run."""
    train = Train(
        id="early-train",
        capacity=800,
        schedule=(
            ScheduledStop("S1", "P1", 100, 130),
            ScheduledStop("S2", "P2", 200, 230),
        ),
        current_delay=-10,
    )
    strategy = STRATEGIES.build(settings.control.strategy)
    return [TrainComponent([train], decision=DecisionPipeline(strategy))]


for name in ("no_control", "schedule_based"):
    selected = replace(scenario, control=parse_control_settings({"strategy": name}))
    result = run_scenario(
        selected, StreamManager, build_components, Path("runs") / name
    )
```

In this example, no-control departs at 120 and 220 seconds. Schedule control
adds a 10-second hold at the first stop, giving departures at 130 and 230.

### Headway regulation

Headway is the time between trains leaving the same platform. Headway regulation
(`headway_regulation`) holds a train when that gap is shorter than the chosen
target. For a 300-second target, a train ready 180 seconds after the previous
train left requests a 120-second hold. The first train leaves without a hold.

Set a target in seconds for each platform; there is no default. This policy uses
actual departure times and ignores the timetable, passenger counts and transfers.
Operating rules can shorten or refuse a hold, so equal spacing is not guaranteed.

```json
{"control": {"strategy": "headway_regulation", "target_headways_s": {"P": 300}}}
```

#### Comparing the three baselines

A, B and C are scheduled to leave at 100, 400 and 700 seconds. Each has a normal
30-second stop, but B arrives 120 seconds early and is ready to leave at 280.
With a 300-second target, both holding policies make B wait until 400:

| Policy | Departures A / B / C | Holds | Gaps between departures |
|---|---|---|---|
| No control | 100 / 280 / 700 s | None | 180 / 420 s |
| Schedule-based | 100 / 400 / 700 s | B waits 120 s | 300 / 300 s |
| Headway regulation | 100 / 400 / 700 s | B waits 120 s | 300 / 300 s |

The difference between the largest and smallest gap falls from 240 seconds to
zero. B uses its earliness to wait, so the hold adds no lateness.

The holding policies can give different results. If A leaves at 200 and B is
scheduled and ready at 400, schedule-based control lets B leave. Headway
regulation holds it until 500 to reach the 300-second gap.

Tests repeat each baseline with fresh trains and the same settings and seed.
They check exact departures and holds, repeatable output files, separate platform
histories, hold limits and departure restrictions after a hold ends. The example
uses fixed inputs, seed 7, a 1000-second run, a 90-second minimum gap and a
300-second maximum hold.

## Team

Built by The Exception Handlers, a Concordia University software engineering capstone team.
