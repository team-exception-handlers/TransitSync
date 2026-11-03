# Person 8 investigation and implementation checklist

AI contribution: 50% or more AI-generated (Codex, OpenAI)

## Verified baseline (2026-11-02)

PR #164 is open, unmerged, targets `main`, and has source branch
`feature/UI-foundation`, HEAD `3994991a66c5ddee16bf353f76fdbf0d9b676c40`.
Its three commits add the shell/data, seeking, then frontend CI. Discussion asks
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
