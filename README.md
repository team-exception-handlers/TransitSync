# TransitSync

[![Continuous Integration](https://github.com/team-exception-handlers/TransitSync/actions/workflows/ci.yml/badge.svg)](https://github.com/team-exception-handlers/TransitSync/actions/workflows/ci.yml)
[![Frontend CI](https://github.com/team-exception-handlers/TransitSync/actions/workflows/web.yml/badge.svg)](https://github.com/team-exception-handlers/TransitSync/actions/workflows/web.yml)
[![Docker Compose CI](https://github.com/team-exception-handlers/TransitSync/actions/workflows/docker.yml/badge.svg)](https://github.com/team-exception-handlers/TransitSync/actions/workflows/docker.yml)
[![Quality Gate Status](https://sonarcloud.io/api/project_badges/measure?project=team-exception-handlers_TransitSync&metric=alert_status)](https://sonarcloud.io/summary/new_code?id=team-exception-handlers_TransitSync)

Every pull request to `main` runs three GitHub Actions workflows:

| Workflow | What it checks |
|---|---|
| [Continuous Integration](.github/workflows/ci.yml) | Python tests with coverage (pytest and Hypothesis), lint and formatting (ruff), SonarQube scan |
| [Frontend CI](.github/workflows/web.yml) | ESLint, Vitest tests, TypeScript type check and production build for `web/` |
| [Docker Compose CI](.github/workflows/docker.yml) | Builds both containers, starts them and checks the backend health endpoint and the front end page |

## Release demos

| Release | Demo video | Release notes |
|---|---|---|
| Release 1 | [Recorded Presentation](https://1drv.ms/v/c/44ad8ea29acb7bf5/IQAXPbx3spOTSbwqgY7HggGNASzoGT_PsayHJIYYqBVG5Lc?e=xyOg6G) | [Release 1 notes](https://github.com/team-exception-handlers/TransitSync/releases/tag/Release_1) · [Slides](https://docs.google.com/presentation/d/10ll2VH4cBHSkHh4KYiL8QeMqWpek6zDXyl2MctDgDbE/edit?usp=sharing) |

Iteration release notes: [Iteration 1](https://github.com/team-exception-handlers/TransitSync/releases/tag/Iteration_1), [Iteration 2](https://github.com/team-exception-handlers/TransitSync/releases/tag/Iteration_2), [Iteration 3](https://github.com/team-exception-handlers/TransitSync/releases/tag/Iteration_3).

## Project summary

TransitSync is a simulation and decision-support tool that tests whether briefly holding a Montréal Metro or REM train at an interchange (a station where riders change lines) helps more people than it hurts. When a REM train arrives, transferring passengers can miss the connecting Metro by a few seconds and then wait a full headway (the time between two trains on the same line) for the next one. Holding the Metro saves them that wait, but it delays everyone already on board and can push back the trains behind it. TransitSync simulates trains and passengers at three interchanges (Gare Centrale / Bonaventure, McGill and Édouard-Montpetit) using real REM and STM schedules, compares holding strategies such as no control, schedule-based holding, headway regulation and connection protection, and replays every decision in a web view so transit planners can see why a train was held or released. It is a one-year SOEN 490 capstone project at Concordia University, built by The Exception Handlers.

## Developer getting started guide

### Prerequisites

| Tool | Version | Needed for |
|---|---|---|
| [Git](https://git-scm.com/) | Any recent version | Cloning the repo |
| [Docker Desktop](https://www.docker.com/products/docker-desktop/) with Docker Compose | Any recent version | Option A (quickest way to run) |
| [Python](https://www.python.org/downloads/) | 3.12 or newer | Option B, running the Python tests |
| [Node.js](https://nodejs.org/) | 22.22.2 or newer | Option B, running the front end tests |

The simulator reads its schedules from files committed in `config/`, so a Supabase account is **not** needed to run the app or the tests. Supabase is only used to re-extract schedule data (see [Supabase and GTFS data](#supabase-and-gtfs-data-optional)).

### 1. Clone the repository

```powershell
git clone https://github.com/team-exception-handlers/TransitSync.git
cd TransitSync
```

### 2. How to run

#### Option A: Docker (quickest)

```powershell
docker compose up --build
```

The first build downloads the base images and installs the pinned dependencies, so it takes a few minutes. When both services are healthy, open:

| Service | URL |
|---|---|
| Front end | <http://localhost:5173> |
| Backend health check | <http://localhost:8000/health> |
| Interactive API documentation (Swagger) | <http://localhost:8000/docs> |

Press `Ctrl+C` to stop. To run in the background, use `docker compose up --build --detach` and stop with `docker compose down`.

The Docker front end is built without an API address, so it only replays the bundled sample runs and the **Run scenario** button is disabled. To run live simulations from the browser, keep the backend running in Docker and start the front end with Option B, step 3.

If the Docker Desktop builder fails with `exec format error`, use a separate BuildKit builder:

```powershell
docker buildx create --name transitsync-builder --driver docker-container
docker compose build --builder transitsync-builder
docker compose up --detach
```

#### Option B: Run locally (for development)

This option runs the backend and front end in two terminals, with live reload on both.

**Step 1. Python environment** (from the repository root, once):

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
```

On macOS or Linux, use `python3.12 -m venv .venv` and `source .venv/bin/activate`. In VS Code, choose `.venv` through **Python: Select Interpreter**. Always run Python tools from the virtual environment, since a system Python will not have the project dependencies.

**Step 2. Start the backend** (terminal 1, repository root, virtual environment active):

```powershell
python -m uvicorn api.main:app --reload
```

The API runs at <http://localhost:8000> and its documentation at <http://localhost:8000/docs>.

**Step 3. Start the front end** (terminal 2):

```powershell
cd web
npm ci
Copy-Item .env.example .env
```

Open `web/.env` and set `VITE_API_URL=http://localhost:8000`, then run:

```powershell
npm run dev
```

Open <http://localhost:5173>. Set `VITE_API_URL=http://127.0.0.1:8000` before starting Vite to enable the Run scenario button. Without `VITE_API_URL`, the front end still starts but only replays bundled sample runs.

### 3. Using the app

1. Pick an interchange connection (Gare Centrale / Bonaventure, McGill or Édouard-Montpetit)
2. In **Run settings**, choose a strategy, the maximum hold, the prediction error, the passenger flow and whether to inject a disruption
3. Press **Run scenario**. The backend simulates one hour of weekday morning service and the station view replays trains, transferring passengers and each hold decision, with a summary of the results

The same run can be started without the front end from the Swagger page with `POST /simulation/run`, for example:

```json
{
  "connection_id": "mcgill-rem-green",
  "strategy": "connection_protection",
  "max_hold_time": 120,
  "error_magnitude": 1,
  "passenger_flow": "Normal",
  "disruption_enabled": false
}
```

Valid connection IDs are `gare_centrale_bonaventure-rem-orange`, `mcgill-rem-green` and `edouard_montpetit-rem-blue`, and `GET /connections` lists them. Valid strategies are `no_control`, `schedule_based`, `headway_regulation`, `connection_protection`, `rolling_horizon` and `adaptive`.

Copy the `run_id` from the run response into `GET /simulation/runs/{run_id}/results` in Swagger. The response contains `passenger_metrics`, the `time_series` delay buckets and hold markers, and `passenger_outcomes` for passenger-level charts. The API keeps the eight most recently used runs in memory. If a run was evicted or the API restarted, submit the same settings again to repopulate the cache.

### 4. Environment variables

| File | Variable | Purpose |
|---|---|---|
| `.env` (copy of `.env.example`) | `SUPABASE_DB_URL` | Supabase PostgreSQL connection string. Only needed for the data extraction scripts |
| `.env` | `SUPABASE_SSL_ROOT_CERT` | Optional path to the Supabase CA certificate |
| Process environment | `TRANSITSYNC_CORS_ORIGINS` | Comma-separated browser origins the API accepts. Defaults to `http://localhost:5173,http://127.0.0.1:5173` |
| `web/.env` (copy of `web/.env.example`) | `VITE_API_URL` | Backend address for the front end, for example `http://localhost:8000` |

`.env` files are git-ignored. Never commit a real connection string or key. The API reads `TRANSITSYNC_CORS_ORIGINS` from the shell, not from `.env`. To allow another origin in PowerShell:

```powershell
$env:TRANSITSYNC_CORS_ORIGINS = "http://localhost:5173,http://127.0.0.1:5173"
```

### 5. Running the tests and checks

These are the same checks CI runs. Python checks run from the repository root with the virtual environment active:

```powershell
pytest -v                 # all Python tests (unit, Hypothesis property, determinism, API)
pytest --cov              # with coverage
ruff check .              # lint, including complexity and function size limits
ruff format --check .     # formatting
docker compose config     # validate the container configuration
```

Performance target tests are opt-in, so CI and a plain `pytest` skip them. They time uncached API requests against the targets on the Performance wiki page and print one table of results:

```powershell
pytest tests/performance -m performance -s
```

Front end checks run from `web/`:

```powershell
npm run lint              # ESLint
npm test                  # Vitest
npm run typecheck         # TypeScript
npm run build             # production build
```

### Supabase and GTFS data (optional)

GTFS (General Transit Feed Specification) is the standard file format agencies use to publish schedules. The raw REM and STM feeds are loaded into a Supabase PostgreSQL database, and the values the simulator needs (platforms, trips, headways) are extracted once into `config/reference_network/`. The simulator never reads GTFS at runtime.

Re-extracting the reference network is only needed when the feeds change. It requires read access to the team's Supabase project:

1. Copy `.env.example` to `.env` and fill in `SUPABASE_DB_URL` (ask a team member for access)
2. Run the extraction into a new folder inside `config/`:

```powershell
python -m scripts.extract_network --output-dir config/reference_network_new
```

The script writes `network.json` and a readable `report.md`, and refuses to overwrite existing output that differs. See the [Reading GTFS data](https://github.com/team-exception-handlers/TransitSync/wiki/Reading-GTFS-data) wiki page for the feed versions and table layout.

### Repository layout

| Path | Contents |
|---|---|
| `simulator/` | Python discrete-event simulator: event engine, trains, passengers, control strategies and safety rules |
| `api/` | FastAPI backend that validates run settings, runs simulations and returns station-view data |
| `web/` | React and TypeScript front end (Vite, Zustand, Canvas 2D station view) |
| `config/` | Committed reference network, station layouts and demo scenarios |
| `scripts/` | One-time GTFS extraction scripts that read from Supabase |
| `tests/` | pytest and Hypothesis tests, mirroring the source tree |
| `AI_USAGE.md` | Record of AI assistance per file and per pull request |

Detailed simulator internals are documented in the [Engine Core Developer Guide](https://github.com/team-exception-handlers/TransitSync/wiki/Engine-Core-Developer-Guide), and every formula is defined on [Mathematical Foundations](https://github.com/team-exception-handlers/TransitSync/wiki/Mathematical-Foundations).

### Contributing

1. Pick an issue from the [project board](https://github.com/orgs/team-exception-handlers/projects/5) and read its parent user story
2. Branch from `main` (for example `feature/<short-name>` or `fix/<short-name>`)
3. Add or update tests, and run the checks above before pushing
4. Open a pull request using the [PR template](.github/pull_request_template.md), including the AI declaration. All three CI workflows must pass, and at least one teammate must approve (two for changes over 250 source lines)

**Project board:** <https://github.com/orgs/team-exception-handlers/projects/5>

## Wiki table of contents

**Project work**
- [Meeting Minutes](https://github.com/team-exception-handlers/TransitSync/wiki/Meeting-Minutes)
- [Sprint Summaries](https://github.com/team-exception-handlers/TransitSync/wiki/Sprint-Summaries)
- [Risks](https://github.com/team-exception-handlers/TransitSync/wiki/Risks)
- [Personas](https://github.com/team-exception-handlers/TransitSync/wiki/Personas)
- [Economic Impact](https://github.com/team-exception-handlers/TransitSync/wiki/Economic-Impact)
- [Budget](https://github.com/team-exception-handlers/TransitSync/wiki/Budget)
- [Missing Knowledge and Independent Learning](https://github.com/team-exception-handlers/TransitSync/wiki/Missing-Knowledge-and-Independent-Learning)

**Design and development**
- [Architecture](https://github.com/team-exception-handlers/TransitSync/wiki/Architecture)
- [Design Patterns](https://github.com/team-exception-handlers/TransitSync/wiki/Design-Patterns)
- [Infrastructure and Tools](https://github.com/team-exception-handlers/TransitSync/wiki/Infrastructure-and-Tools)
- [Naming Conventions](https://github.com/team-exception-handlers/TransitSync/wiki/Naming-Conventions)
- [Testing Plan and Continuous Integration](https://github.com/team-exception-handlers/TransitSync/wiki/Testing-Plan-and-Continuous-Integration)
- [Security](https://github.com/team-exception-handlers/TransitSync/wiki/Security)
- [Performance](https://github.com/team-exception-handlers/TransitSync/wiki/Performance)
- [Deployment](https://github.com/team-exception-handlers/TransitSync/wiki/Deployment)
- [Mockups](https://github.com/team-exception-handlers/TransitSync/wiki/Mockups)

**Technical reference**
- [Mathematical Foundations](https://github.com/team-exception-handlers/TransitSync/wiki/Mathematical-Foundations)
- [Engine Core Developer Guide](https://github.com/team-exception-handlers/TransitSync/wiki/Engine-Core-Developer-Guide)
- [Reading GTFS data](https://github.com/team-exception-handlers/TransitSync/wiki/Reading-GTFS-data)

**Responsibilities**
- [User Consent and License Agreement](https://github.com/team-exception-handlers/TransitSync/wiki/User-Consent-and-License-Agreement)
- [Legal and Ethical Issues](https://github.com/team-exception-handlers/TransitSync/wiki/Legal-and-Ethical-Issues)
- [Diversity Statement](https://github.com/team-exception-handlers/TransitSync/wiki/Diversity-Statement)

## Data credit

Schedule data from the Réseau express métropolitain (REM), https://rem.info, used under CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/). Data has been processed and modified for this project.

Schedule data from the Société de transport de Montréal (STM), https://www.stm.info, used under CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/). Data has been processed and modified for this project.

## Licence

Released under the [MIT License](LICENSE).

AI acknowledgement: this README was drafted with Claude and reviewed and edited by the team. AI use across the project is recorded in [AI_USAGE.md](AI_USAGE.md).
