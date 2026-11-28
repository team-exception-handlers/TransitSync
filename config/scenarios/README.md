# Release demo scenarios (#189)

Each JSON file selects one connection for the simulation run endpoint (#180).
All use the committed reference network's weekday date, 2026-10-05, at 07:00
America/Toronto for one hour, one repetition, and master seed 42. They differ
only in the selected interchange.

`reference-network` is the dataset identifier chosen for these files. The #180
endpoint must register matching `DatasetMetadata` for
`config/reference_network/network.json` under that identifier. No dataset ID
was previously specified by #180; this is an integration contract to coordinate,
not an existing runtime registration.

The files omit `control`, `operating_rules` and `parameters` so the scenario
loader supplies its defaults (maximum hold 300 seconds, minimum safe gap 60
seconds, 60 transferring passengers per REM train, the GTFS timetable, 300
passengers on board, a 120-second mean walk). The run endpoint is responsible
for applying and validating run-settings overrides, including strategy,
maximum hold, prediction error, the scenario parameters (#258), a time-of-day
preset, and disruption settings. These base files are not rewritten when settings change.

AI assistance for these JSON files and this note is recorded in `AI_USAGE.md`.
