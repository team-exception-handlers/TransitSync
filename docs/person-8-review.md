# Person 8 investigation and implementation checklist

AI contribution: 50% or more AI-generated (Codex, OpenAI)

## Verified baseline (2026-11-02)

PR #164 is open, unmerged, targets `main`, and has source branch
`feature/UI-foundation`, HEAD `3994991a66c5ddee16bf353f76fdbf0d9b676c40`.
Its initial three commits add the shell/data, seeking, then frontend CI. Discussion asks
for tests; one review approves and there are no inline review comments.
Baseline: 60 tests pass; ESLint, TypeScript and Vite build pass.

Repository: Python discrete-event simulator (`simulator/`), saved GTFS topology
(`config/`), extraction scripts (`scripts/`), pytest/Hypothesis tests (`tests/`),
and independent React/Vite/TypeScript frontend (`web/`). No API exists yet.
The Python heap queue uses deterministic event ordering and seeded streams;
playback must read recorded results, never rerun or alter the simulator.
The wiki architecture still mentions PixiJS/D3 and Jest; #152 and actual source
use Canvas 2D and Vitest. Follow the issue and installed architecture.

### Person 9 audit

| Deliverable | Correct | Missing / limits |
| --- | --- | --- |
| #150 mockups (3.1.7) | Wiki Mockups documents station, picker and playback; supplied Figma has playing, paused, unloaded and all three station frames | PR shell intentionally omits most composed UI |
| #151 format/mock | Versioned TS contracts; backend platform IDs/directions; validated McGill mock with pulse and train events | Wiki format/agreement with Persons 2/7/8 not evidenced; no simulator-output adapter; train load/hold fields absent |
| #152 shell | React/Vite/TS, Zustand, responsive CSS and mock loading | Required Canvas component absent; station region empty |
| #84 state/time | Authoritative time, clamped arbitrary seek, pure snapshots, walking interpolation, backward reconstruction | Playback state/clock deliberately deferred to Person 8; station consumers absent |
| Lint/tests/CI | ESLint, 60 Vitest tests, Node 22 CI runs lint/tests/typecheck/build | Installed Node 24.0.1 is older than jsdom's supported 24.15; tests nevertheless pass; lockfile audit reports 12 moderate vulnerabilities |

Small prerequisite correction: supply a data-driven Canvas consumer and its test,
separately from feature work. No redesign of the data contract or simulator.
Validation is useful but not a complete hostile JSON boundary (some nested
malformed items can produce generic errors); outside this local mock workflow.
Snapshots sort train events per query; sufficient for the current small fixture,
but a future large-run adapter should index events before playback.

## Requirements and decisions established before implementation

Read full issues #75, #76, #80–#87, #150–#152 and parent stories #66–#68;
all task issues have zero comments. Parent stories were retrieved in full.

| Issue | Required behavior | Components / tests planned |
| --- | --- | --- |
| #75 | Choose a connection; load its data on change | Shared store selection, selector; active state, invalid/unavailable selection |
| #76 | Three named interchanges with metro lines | Backend mapping-based catalog, mock datasets; all IDs/directions, switching/reset, Canvas consumer |
| #80 | Play from current position; disabled without run | Store play + frame clock, control; no run/end/duplicate play, progression |
| #81 | Pause retaining position and visible state | Store pause + toggle; pause/resume and frozen snapshots |
| #82 | Earlier time, rebuild display, work while running | Rewind 30 s (Figma/wiki); clamp at zero, running/paused/end, reconstructed passengers |
| #83 | Responsive controls consistent with running state | One clock owner + Zustand; StrictMode, cleanup, scrubbing, connection changes, state/clock/Canvas integration |
| #85 | 0.5×, 2×, 10× options, active indication | Segmented selector; parent #68 and Figma additionally require normal 1× |
| #86 | Apply speed without interruption | Store speed validation; paused/running changes, no reset or duplicate frames |
| #87 | Simulated seconds = real seconds × speed; smooth high speed | Monotonic elapsed-time clock; fractional and irregular frames, mid-frame changes, identical snapshots at equal simulation times |

Connection changes reset to zero and pause (selecting the already active entry
is a no-op); the user can start the new run explicitly. This makes the parent's
"playback resets" deterministic without starting an unrequested run. Preserve
the chosen speed. Mock data for additional stations must be visibly identified
as synthetic and use actual platform metadata, not invented station identities.
At run end pause exactly at duration; Play remains disabled until rewind/seek.

Figma MCP session: `2494e828-5d34-46a4-b066-4307c3606578`.
Inspected hierarchy on Mockups page `0:1`, station playing `4:2`, connection
component `4:12`, playback `4:356`, unloaded picker `4:427`, McGill `11:520`,
Édouard-Montpetit `12:655`, paused Play `5:587`. Design context and initial
screenshot retrieved. Colors, IBM Plex type, 52px segmented groups, 44px
buttons, 18px icons, 30-second rewind and four speed values guide implementation.
Keep existing timeline/data duration (07:40–07:46); do not fabricate the mockup's
hour-long run, metrics, seed, decisions or passenger totals.

## Git conventions

Wiki Naming Conventions: type/issue-short-name; new branch
`feat/75-playback-speed-connections` starts exactly at Person 9 HEAD.
Project code-workflow: imperative component summary with issue references and
AI-assisted trailer. User explicitly authorizes local commits, overriding local
Claude instructions that reserve commits for the team. No pushes, merges or PRs.
Existing camel/Pascal-case frontend filenames are preserved for consistency.
No new dependency is planned. Design-pattern wiki text will be drafted locally
in this repository for team review; the remote wiki remains unchanged.

## Delivered behavior and tests

All nine tasks are implemented. Existing `getNetworkSnapshot`, station-view
contracts, validation and the mapping adapter remain the playback foundation.
New state lives in `web/src/store/usePlaybackStore.ts`; there is no component
playback state or Python simulation change. `currentTime_s` is the committed
display position. `anchorTime_s` plus the monotonic millisecond timestamp define
the current constant-speed segment. Frames derive position from that fixed
origin; user actions settle or replace it atomically, preventing frame-count
drift and partial-frame speed jumps.

| Issue | Implementation | Relevant tests |
| --- | --- | --- |
| #75 | `components/connection-selector.tsx`, store catalog/selection actions; native buttons and pressed feedback | `components/connection-selector.test.tsx`: loading, active indicator, same-selection no-op, unknown/duplicate IDs |
| #76 | `data/connection-runs.ts`, App station heading, shared Canvas; three real names, lines, platform IDs and directions; resets/pause on change | `data/connection-runs.test.ts`, selector tests, `components/playback-integration.test.tsx`: all identities, validated endpoints, running switch |
| #80 | `components/playback-controls.tsx`, store `play`, `lib/playback-clock.ts`; start/resume from current position | `components/playback-controls.test.tsx`, `playback/playback-clock.test.ts`: disabled without run, zero duration/end, repeated Play, progression |
| #81 | Shared Play/Pause toggle and store `pause`; settle fractional elapsed time, retain snapshot | Controls/clock tests: pause, frozen state, resume and UI feedback |
| #82 | Store `rewind30`, original Figma icon; subtract 30 simulated seconds and reconstruct display | Controls/clock/Canvas tests: paused/running/completed/beginning, fractional rewind and exact passenger coordinates |
| #83 | Single leased frame subscription, idempotent cleanup, isolated `components/simulation-clock.tsx`; responsive layout | Clock/integration tests: StrictMode, multiple consumers, cleanup, seeks, replacement/invalid data, clock/slider/Canvas synchronization |
| #85 | `components/speed-selector.tsx`, `types/playback-speed.ts`; four pressed-state segments | `components/speed-selector.test.tsx`: exactly 0.5/1/2/10, current speed, disabled without run |
| #86 | Store `setSpeed`; reject invalid values, settle old rate, retain playback/paused position | Speed/clock tests: live and paused changes, same-speed selection, invalid factors, preserved speed on connection switch |
| #87 | Fixed-origin `performance.now()` timing and frame-driven updates, no timer restart on rate changes | Clock/integration tests: fractional/irregular frames at all speeds, multiple changes within a frame, pause/resume/rewind/end at every speed, equal-time snapshots and unchanged source data |

All paths in the table are relative to `web/src/` or `web/tests/`, respectively.
Existing tests asserting the deliberate *absence* of Person 8 controls/Canvas
were replaced with assertions of their delivered behavior; seek/snapshot tests
were retained. New tests use hand-calculated coordinates/times, fake frames or
fake timers. No test/lint configuration or dependency was weakened or changed.

## Figma implementation and limitations

Implemented the header's connection segments, paired line swatches, selected
dark segment, playback Play/Pause toggle, 30-second rewind, four speed segments,
keyboard focus states and touch target sizes. Native buttons use `aria-pressed`
and accessible names; line names supplement color. Reused the shell's plain CSS
and typography, adding the previously referenced IBM Plex Mono font to its font
import. Original 18×18 Play/Pause/Rewind SVGs are local in `web/public/playback`.

Deliberate limits: the Canvas consumes the existing 800×600 synthetic geometry;
the other interchanges reuse that fixture geometry. This is a small correction
to the missing shell consumer, not full US-3.1 station artwork. Existing empty
inspector panels, omitted future navigation, train loads, hold decision log,
hour-long mockup timeline, event markers and passenger inspection remain outside
Person 8. They cannot be honestly populated with the current contract's fields.
The actual fixture is 07:40–07:46 and remains labeled as mock playback.

Rendered visual QA was attempted: Vite built and served successfully, but the
in-app browser could not reach localhost. Local Chrome automation then stopped
because its policy could not verify the current browser URL. UI automation was
stopped. No screenshot-level match, mobile screenshot check or browser blackbox
run is claimed. A human browser comparison remains recommended.

## Validation

- Person 9 baseline: 60 frontend tests passed; lint, typecheck and build passed
- Final frontend: 107 Vitest tests in 13 files passed; `npm run lint`,
  `npm run typecheck`, `npm run build` passed from `web/`
- Backend: `.venv/Scripts/python.exe -m pytest -x -q --basetemp=C:/TransitSync/.local/pytest`
  passed all 770 tests, including determinism; Python lint and format checks pass
- `git diff --check` and staged checks pass
- Initial Python collection lacked pinned psycopg/dotenv packages. Installing
  existing `requirements-dev.txt` into `.venv` resolved collection. The default
  pytest temp directory was inaccessible under the sandbox (136 setup errors);
  using the explicit workspace temp directory resolved all errors
- Lockfile audit reports 12 inherited moderate vulnerabilities and Node 24.0.1
  reports an engine warning for jsdom (requires 24.15+ on the Node 24 line).
  Node 22 remains the CI configuration; packages were not upgraded for this task
- No dependency, Python source, CI workflow or Person 9 commit was changed

## Local Git history

Source branch: `feature/UI-foundation`, verified starting commit
`3994991a66c5ddee16bf353f76fdbf0d9b676c40`. New local branch:
`feat/75-playback-speed-connections`, with no upstream configured.

During final verification, Person 9 added attribution-only commit
`2b4a5551061130e14241d27f6affb75b550a6542`. The nine local Person 8 commits were
replayed onto that latest source HEAD, preserving Person 9's commit exactly.
Two attribution-header conflicts were resolved using the accurate Person 8 AI
level and module description; no runtime conflicts occurred. Comparison with
the pre-replay feature tip shows only Person 9's new attribution changes.
Frontend checks were rerun after the replay. Final base is therefore `2b4a555`.

| Commit | Message / issues |
| --- | --- |
| `49670a6` | Add missing station Canvas consumer for UI foundation (#152) |
| `7333e14` | Add shared connection selection and run loading (#75) |
| `346467a` | Display all three mapped REM–Metro connections (#76) |
| `0578d0b` | Implement Play and Pause with monotonic playback clock (#80, #81) |
| `e6b1048` | Rewind recorded playback by 30 simulated seconds (#82) |
| `1734c28` | Synchronize playback lifecycle and shared views (#83) |
| `e1884f0` | Add validated playback speed selection and controls (#85, #86) |
| `e330757` | Anchor speed-scaled timing independently of frame frequency (#87) |
| `d797371` | Polish responsive controls and document playback contracts (#75, #83, #87) |

A final report-only commit records this validation and the updated base/history.
Its hash is included in the chat delivery. Play/Pause were grouped because they share a
toggle and lifecycle. Speed selector/control were grouped so every option
already affects playback in its first commit. Tests were run incrementally
before commits; only explicit task files were staged and staged diffs reviewed.

No push, merge or PR was performed. The original train branch remains at
`a56a3d5`; Person 9's branch and commits were not edited. Downloaded wiki and
temporary test outputs live under locally excluded `.local/`.

## Review notes and next steps

Local wiki drafts: `docs/person-8-wiki-drafts.md` (Observer, fixture Adapter,
playback format); no remote wiki changes or new library comparisons are needed.
Agreement on #151 with Persons 2/7/8 is still a team follow-up. The backend-output
adapter must reconcile simulator station IDs and schema with the frontend mock
contract; full station artwork/metrics remain downstream work.

Files stay below 500 lines (App.css: 489; store: 227 before final comments).
`cloc` is not installed. Approximate comment/nonblank ratios from a local script
were: selector 25.7%, playback controls 24.2%, speed selector 27.6%, Canvas 15.4%,
fixture adapter 19.6%, frame clock 15.2%, store 12.3%; existing App and tests are
also below the project's 20–30% target. Comments explain new state/lifecycle
decisions; padding existing code or tests merely to hit a ratio was avoided.
The combined source change exceeds the wiki's 400-line single-PR target;
review connections, playback and speed commits as separate stacked review units
when the team later prepares PRs. No PR split or submission was performed here.
