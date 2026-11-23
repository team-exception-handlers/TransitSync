# AGENTS.md

Instructions for Codex and other coding agents that read `AGENTS.md`.

## Project rules

The project rules live in [`.claude/CLAUDE.md`](.claude/CLAUDE.md). Read that whole file before starting any task and follow it exactly as if it were written here. It covers the scope, repository layout, stack, commands, simulator rules, data and secrets handling, the read-only GitHub policy, team code rules, tests and writing style.

This file only adds what is different for agents other than Claude Code. If the two files disagree, `.claude/CLAUDE.md` wins.

## Skills

- Codex loads project skills from `.agents/skills/`. Right now that folder only has `grilling`
- The other project skills (`code-workflow`, `sim-logic`, `gtfs-data`, `python-tests`, `sonar-clean-code`, plus the generic ones) are in `.claude/skills/<name>/SKILL.md`. When `.claude/CLAUDE.md` says to follow a skill, open that file and follow it
- Use `grilling` when someone asks to be grilled or to stress-test a plan, design or decision before any code is written
- `.claude/skills/grilling/` and `.agents/skills/grilling/` must stay identical. Change both together

## Commands

The commands in `.claude/CLAUDE.md` use Windows paths (`.\.venv\Scripts\python.exe`). On macOS or Linux, use `.venv/bin/python` instead.
