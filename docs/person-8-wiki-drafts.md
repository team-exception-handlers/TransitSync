# Person 8 wiki drafts (local only)

AI contribution: 50% or more AI-generated (Codex, OpenAI)

## Design Patterns: Observer for the shared playback clock

- Where: `web/src/lib/playback-clock.ts`, `startPlaybackClock`
- Problem: #83 and #87 require responsive shared controls without concurrent timers
- Application: one Zustand subscription requests at most one animation frame.
  Mounted views lease that subscription; only the last cleanup stops it. The
  store owns all position, playing-state and speed transitions
- Reason: per-button timers can diverge and duplicate under StrictMode. A shared
  frame driver follows browser rendering and leaves calculation in the store
- Added in: local Person 8 branch; no PR opened

## Design Patterns: existing Adapter extended for connection fixtures

- Where: `web/src/data/connection-runs.ts`, `buildMockRun`, using Person 9's
  `buildStationViewData` adapter
- Problem: #76 needs all three real connection identities while only McGill has
  playback fixture data
- Application: reuse the synthetic geometry and pulse, remap station/platform/
  corridor/connection references to the saved mapping, then validate the result
- Reason: avoids copied JSON fixtures and a second data model. These are labeled
  mock runs; real geometry and simulator results remain a future integration
- Added in: local Person 8 branch; no PR opened

## Playback data format (#151 documentation draft)

`web/src/types/stationView.ts` defines frontend schema version 1. Time values are
elapsed simulation seconds; `start_clock_s` is the displayed clock offset and
`duration_s` bounds all seeks. `map` contains Canvas coordinates and dimensions.
Stations/platforms carry positions; platforms preserve the saved GTFS line,
direction, stop and feed IDs. Corridors contain endpoint IDs and polyline paths.
Connections associate two platforms with a corridor and human-readable label.

Passenger tracks contain `passenger_id`, `group_id`, `connection_id` and ordered
samples (`time_s`, `position`, `phase`). Walking positions interpolate between
samples; queued/waiting/boarding states hold their last coordinate; boarded
passengers disappear. The pure snapshot query reconstructs any earlier time.

Train arrival/departure events carry train/platform IDs, `time_s`, `scheduled_s`,
and `station_id`. The existing mock validator requires event `station_id` to
equal the saved platform's **stop ID**. This frontend contract is distinct from
the Python simulator event schema (currently version 4), whose runtime network
uses interchange identities. A simulator-output adapter must explicitly resolve
these identities; raw event logs cannot be treated as StationViewData.

`loadData` validates before changing state, resets time to zero, pauses and
defaults to 1×. `setAvailableRuns` validates a catalog with unique connection IDs.
`selectConnection` resets time and pauses, preserving speed; selecting the same
connection does nothing and unknown IDs raise an error. `getSnapshotAt` never
moves the current position. Play at the end is disabled until seek/rewind.

Playing time uses `anchorTime_s + elapsed_wall_seconds × speed`. Pause, seek,
rewind and speed changes settle/reanchor atomically. Speeds are 0.5, 1, 2 and 10.
Rewind subtracts 30 simulated seconds and preserves running/paused intent.

This draft has not been posted to the wiki or agreed with Persons 2/7/8 on their
behalf. The team should review the adapter boundary before connecting real logs.

## Library Comparisons

No new library was added for Person 8. Existing React, Zustand, Vitest and Testing
Library are reused. Browser `performance.now` and `requestAnimationFrame` need
no package or library-comparison entry. Person 9's dependency documentation is
not retroactively claimed complete by this draft.
