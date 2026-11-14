---
name: sonar-clean-code
description: Use when writing, changing or reviewing TransitSync code (Python simulator, scripts and API, pytest tests, TypeScript/React front end, CI workflows) so new code does not add SonarQube Cloud issues. Lists every rule the project has been flagged for, the pattern that triggers it, the fix, and the local check that catches it before a push.
---

# Keep new code SonarQube clean (TransitSync)

SonarQube Cloud scans every PR (`team-exception-handlers_TransitSync`). Iteration target: **0 high issues, at most 30 medium**, and no new issues in any PR. This skill lists the rules the project has already hit, what triggers each one, and how to write code that does not trigger it. It sits alongside `code-workflow` (rubric) and `python-tests` (test design). If anything here conflicts with `CLAUDE.md`, `CLAUDE.md` wins.

Snapshot on 2026-10-31: 68 open issues. 49 are S5778 and 13 are S9073, all in tests. Fixed or accepted so far: S3776 (8), S8572 (4), S8707 (2), S7519 (2), S8544 (1).

Release 1 high issues (2026-11): all 13 fixed. S8495 (5), S1192 (1), S3776 in Python (4) and S3776 in TypeScript (3).

**Scope:** apply these rules to code you write or change. Do not fix existing issues in untouched code as part of an unrelated task; existing issues are cleaned up in dedicated refactoring work. If a task touches a function that already has an issue, mention it at the end instead of fixing it, unless the task is that refactoring.

## Run before every commit

Ruff catches several Sonar rules locally. They are not in `pyproject.toml`, so run them explicitly. Existing code already has hits; only the files you added or changed need to be clean:

```
.\.venv\Scripts\python.exe -m ruff check . --extend-select PT012,PT018,A001,A002,C420,TRY400
```

| Ruff rule | Sonar rule it matches |
|---|---|
| PT018 composite assertion | S9073 (exact match) |
| PT012 several statements in `pytest.raises` | S5778 (partial: Sonar also counts several calls in one statement, so still check by hand) |
| A001, A002 builtin shadowing | S5806 |
| C420 dict comprehension with a constant value | S7519 |
| TRY400 `error` instead of `exception` in `except` | S8572 (see the CLI exception below) |

Ruff's C901 limit of 15 is cyclomatic complexity, which ignores nesting. Sonar's S3776 is cognitive complexity, which adds a point for every level of nesting. Passing C901 does not mean passing S3776; follow the S3776 rules below.

For the front end, run these from `web/`:

```
npm run typecheck
npm run lint
npm test
```

- `eslint-plugin-sonarjs` is **not installed yet**, so ESLint does not catch the Sonar rules below. Until it is added (in its own PR, with a Library Comparisons wiki entry as `CLAUDE.md` requires), check the TypeScript table by hand and read the SonarQube PR scan
- Windows: run Vitest from a path that starts with an uppercase `C:\`. A lowercase `c:\` path makes Vitest load twice and fail with "Cannot read properties of undefined (reading 'config')"
- A local `web/.env` that sets `VITE_API_URL` makes 2 API tests fail on your machine only. Stash your change and rerun: if they still fail, they are not yours, and CI (no `.env`) decides

## Python tests (most of the open issues)

### S5778: only one call that can raise inside `pytest.raises`
Sonar counts every function call inside the block, including constructors, `str()`, `Path()` and helper calls used to build arguments. Build everything first, then put only the call under test inside the block.

```python
# Flagged: StreamManager(42) could also raise
with pytest.raises(ValueError, match="unique"):
    TransferComponent([configured, configured], StreamManager(42))

# Clean
streams = StreamManager(42)
routes = [configured, configured]
with pytest.raises(ValueError, match="unique"):
    TransferComponent(routes, streams)
```

Same for CLI tests: build the argument list before the block (`argv = ["--mapping", str(path)]`). One `pytest.raises` per case; when a test checks several bad inputs, use `@pytest.mark.parametrize` instead of several blocks in one test.

### S9073: one condition per `assert`
```python
assert "2026-10-05" in caplog.text and "no active services" in caplog.text   # flagged
assert "2026-10-05" in caplog.text                                         # clean
assert "no active services" in caplog.text
```
Separate asserts also tell you which condition failed.

### S5863: actual and expected must not be the same expression
```python
assert generate() == generate()      # flagged, reads as comparing a thing with itself
first = generate()                    # clean, and it states the intent (determinism)
second = generate()
assert first == second
```

### S8997: never change global state by hand in a test
Do not assign to module attributes, class attributes or `os.environ` directly; the change leaks into other tests. Use the `monkeypatch` fixture, which undoes the change after the test.
```python
module.OUTPUT_ROOT = tmp_path                        # flagged
monkeypatch.setattr(module, "OUTPUT_ROOT", tmp_path)  # clean
monkeypatch.setenv("SUPABASE_DB_URL", "postgresql://test")
```

## Python source code

### S3776: cognitive complexity at most 15
This is the most common critical issue (8 fixed before Release 1, 4 more in the Release 1 cleanup). Sonar adds 1 for each `if`, `elif`, `else`, loop, `except`, ternary and run of `and`/`or`, plus 1 more for every level the structure is nested. A check inside a loop inside another loop is expensive.
- Keep at most two levels of nesting inside a loop. When a third appears, move the inner block into a helper
- Validate one item per helper: the loop collects, the helper checks (`_service_window`, `_check_platform_stop`, `_check_stop_time`, `_mapping_platform` in `scripts/`)
- A parser that checks several fields in a row: one helper per field or per kind of field, so the parser is a flat list of `if "x" in value: kwargs["x"] = _parse_x(...)`. Two fields with the same check and a small difference share one helper with a keyword flag (`_rule_seconds(..., allow_zero=True)` and `_parse_rule_action_map` in `simulator/control/settings.py`, which was at complexity 21)
- Replace `if kind == A ... elif kind == B ...` chains with a lookup table of small functions (`_FIELD_CHECKS` in `simulator/engine/events.py`). The same works for `if issubclass(cls, A) ... if issubclass(cls, B)` chains: one builder per class in an ordered table (`_builders()` in `simulator/control/registry.py`, which was at complexity 27)
- A factory with many optional keyword arguments: bundle them in one frozen dataclass and give each case its own small builder that checks only its own inputs. Shared checks ("X required", "Y only valid for Z") become helpers, so each message is written once
- Use guard clauses (`if bad: raise`) instead of wrapping the rest of the function in `if`/`else`
- Never repeat a loop that already exists elsewhere; share one helper (`_check_chronological` in `simulator/trains/train.py`)
- Per-iteration setup inside a loop (where to start, what carries over) belongs in a small function that returns those values. A ternary that only differs on the first pass (`x if index == 0 else 0.0`) becomes a value set before the inner loop and reset after its first use (`_trip_start` in `simulator/trains/train_component.py`, which was at complexity 18)
- A nested function (closure) counts toward the function that contains it. Keep closures to a few lines, and move loops that call them into separate helpers (`_seed_single_station_moves` in `simulator/control/bounded_search.py`)
- Aim for 12 or less so later changes have room

### S8707: path traversal from command-line or request input
Any path that comes from `argparse`, an environment variable or an API request must be resolved and checked against an allowed folder before it is read or written.
```python
def _contained(path: Path, root: Path) -> Path:
    resolved = path.resolve()
    if not resolved.is_relative_to(root.resolve()):
        raise ValueError(f"path must be inside the {root.name}/ folder")
    return resolved
```
Call it in the function that opens the file, not only in `main()`, so the check sits next to the read or write. In the FastAPI layer, accept IDs (scenario ID, run ID), never file paths.

### S8572: `logging.exception()` in exception handlers
- Simulator, API and library code: an unexpected failure (disk, database, bug) uses `log.exception(...)`, so the traceback is kept in the logs
- CLI handlers that catch expected, already-cleaned errors (bad input, `SupabaseReadError`) keep `logger.error(...)`, because those logs go to the user's terminal and `CLAUDE.md` forbids showing tracebacks to users. Mark the line `# noqa: TRY400` with a comment giving that reason, and mark the Sonar issue Accepted (template below)

### S5713: do not list an exception that a broader one in the same `except` already catches
Common pairs: `UnicodeError` and `json.JSONDecodeError` are subclasses of `ValueError`; `FileNotFoundError` and `PermissionError` are subclasses of `OSError`; `KeyError` and `IndexError` are subclasses of `LookupError`.
```python
except (OSError, UnicodeError, ValueError):   # flagged: UnicodeError is a ValueError
except (OSError, ValueError):                 # clean, catches the same errors
```

### S5806: do not shadow a builtin
Avoid `id`, `type`, `input`, `list`, `dict`, `filter`, `map`, `min`, `max`, `sum`, `format`, `hash`, `next`, `open`, `credits`, `license`, `copyright` as variable or parameter names. Name what the value is: `train_id`, `event_type`, `credit_lines`.

### S5864: comparisons Sonar cannot prove are safe
Sonar does not narrow types after `type(value) is not int`. Use `isinstance`, rejecting `bool` first because `bool` is a subclass of `int`:
```python
if type(value) is not int or value < minimum:                        # flagged
if isinstance(value, bool) or not isinstance(value, int):           # clean
    raise ValueError(f"{field} must be an integer")
if value < minimum:
    raise ValueError(f"{field} must be >= {minimum}")
```

### S5886: `dataclasses.replace` loses the return type
`replace()` is typed as returning a generic dataclass, so returning its result from a function annotated `-> TrainState` (or any other frozen dataclass) is flagged. This hit 6 places in `simulator/control/`, because the simulator copies frozen dataclasses everywhere. Wrap the call so the concrete type comes back:
```python
def plan(...) -> HorizonPlan:
    return replace(best, exact=exact)                     # flagged

# Clean: a module that copies several record types (prediction_error.py)
def _updated[Record](record: Record, **changes: object) -> Record:
    """Copy a frozen dataclass with ``changes``, keeping its own type."""
    return replace(record, **changes)

# Clean: a single call (rolling_horizon.py)
return cast(HorizonPlan, replace(best, exact=exact))
```
Use the `_updated` helper when a module has more than one `replace`; a `cast` is fine for a lone call.

### S7519: `dict.fromkeys` for a constant value
`{key: 0 for key in keys}` becomes `dict.fromkeys(keys, 0)`. Only for immutable values: `dict.fromkeys(keys, [])` shares one list between every key, so keep the comprehension for lists, sets and dicts.

### S8495: every return of a function gives a tuple of the same length (reliability, high)
Sonar treats tuple literals as fixed-size records, so returning `()` on one path and `(item,)` on another reads as a bug: a caller that unpacks the result would fail. This hit the API and every strategy's `decide()` (5 issues). When the result is really a variable-length collection (`tuple[Action, ...]`), build it one way and convert once:
```python
if not enabled:                      # flagged: () here, (injection,) below
    return ()
return (injection,)

injections = []                      # clean: one return, any length
if enabled:
    injections.append(injection)
return tuple(injections)
```
When the tuple is a fixed record (`tuple[float, str]`), every path must return the same number of items, or use a small dataclass instead.

Strategies: when `evaluate` can either hold or not, never mix `return ()` with `return (HoldAction(...),)`. Build the hold (or `None`) and return `as_actions(hold)` from `simulator/control/interface.py`. A strategy that never holds (`NoControlStrategy`) may return `()` on its only path.

### S1192: the same string literal written three or more times (maintainability, high)
Sonar flags any string repeated 3+ times in a file, which usually means an error message copied into several `raise` statements of one validator (`simulator/trains/door_throughput.py`). Put it in one module constant next to the imports, with a short comment saying which checks share it:
```python
# One message for every invalid scheduled dwell, so the type, overflow and
# range checks in DoorThroughput.budget report the same error.
_INVALID_DWELL = "scheduled_dwell_s must be finite and non-negative"
...
raise ValueError(_INVALID_DWELL)
```
Better still, when several checks reject the same field with the same message, combine them into one condition or one helper so the message appears once naturally. Dictionary keys and event field names repeated across a file count too; use the constants that already exist (for example in `simulator/control/decision_audit.py`) instead of retyping them.

## CI and dependencies

### S8544: install only locked versions
- Python: every package pinned with `==` in `requirements.txt` / `requirements-dev.txt`
- Front end: commit `package-lock.json` and install with `npm ci`, never `npm install`, in CI
- Pin GitHub Actions to a release tag (`actions/setup-node@v4`), never a branch

### S6505: `npm ci --ignore-scripts` everywhere
A plain `npm ci` runs every dependency's `preinstall`/`postinstall` script, so one compromised package can run code in CI or the image build. Flagged in both `.github/workflows/web.yml` and `web/Dockerfile`.
```
npm ci                    # flagged
npm ci --ignore-scripts   # clean
```
Apply it to every install line (workflows and Dockerfiles). If a new package really needs its install script, run that one step explicitly (`npm rebuild <package>`) and say why in a comment.

## TypeScript and React (front end starting in Iteration 3)

These are the rules Sonar raises on React code; write to them from the first commit.

### S6819: use the native element, not an ARIA role
The most common front-end issue (5 fixed). Sonar flags `role="..."` whenever an HTML element already has that meaning built in, because native elements work on more screen readers.

| Avoid | Write instead |
|---|---|
| `<div role="group" aria-label="Speed">` (segmented controls, button groups) | `<fieldset aria-label="Speed">` |
| `<small role="status">{statusText}</small>` | `<output>{statusText}</output>` |
| `<div role="img">` around a canvas or picture | `<img alt="...">` or `<canvas aria-label="...">` |

`<fieldset>` brings a default border, padding and `min-width`, so reset them once in CSS (see `:where(fieldset.segmented-control, ...)` in `web/src/App.css`) rather than per component. Add a short comment where the element replaces a role, so nobody adds the role back.

| Rule | Avoid | Write instead |
|---|---|---|
| S3358 nested ternary | `a ? x : b ? y : z` | an extracted variable, `if`/`else`, or a lookup object |
| S6479 array index as React key | `items.map((p, i) => <Marker key={i} />)` | a stable ID: `key={p.passengerId}`, `stationId`, `platformId` |
| S1128 unused import | imports left after a refactor | remove them (the editor marks them) |
| S1481, S1854 unused variable or useless assignment | `const result = compute();` never read, or a value overwritten before use | delete it, or use it |
| S6759 props must be read-only | `function Bar(props: Props)` | `function Bar(props: Readonly<Props>)` |
| S6481 context value recreated every render | `<Ctx.Provider value={{ time, setTime }}>` | `const value = useMemo(() => ({ time, setTime }), [time]);` |
| S3776 cognitive complexity | long render functions with nested conditions | split into small components and hooks |
| S1186 empty function | `onClick={() => {}}` placeholders | implement it, or leave a comment saying why it is empty |
| S4325 unnecessary cast or `!` | `value as number` when it is already a number | remove it; fix the type at its source |
| S6853 form label not linked to a control | `<label>Speed</label><select>` | `<label htmlFor="speed">Speed</label><select id="speed">` |

Keep simulation state in the Zustand store and keep components presentational. That keeps render functions short (S3776) and avoids context-value churn (S6481).

### S3776 in TypeScript (3 high issues in Release 1)
The same cognitive complexity rule applies to `.ts` and `.tsx`, and callbacks count toward the function they sit in, including the arrow function passed to `useEffect`.
- **Canvas drawing in `useEffect`:** one module-level function per drawing step (`sizeCanvas`, `drawCorridors`, `drawPlatforms`, `drawTrains`, `drawPassengerCount` in `web/src/components/station-canvas.tsx`, which was at 16). The effect becomes a short list of calls, and each helper takes the 2D context and only the data it draws
- Move fallback choices such as `a && a.width > 0 && a.height > 0 ? a : fallback` into a named helper (`chooseView`)
- **Data builders and adapters:** same rule as the Python mapping code. The loop collects and checks what needs shared state (duplicates); one helper checks and builds a single item; header checks and "every X is used" checks get their own functions. `web/src/lib/buildStationViewData.ts` went from 28 to a four-line entry function this way (`checkMockHeader`, `collectPlatforms`, `toPlatform`, `checkEveryLayoutIsMapped`)
- **Validators with one loop per collection:** when several loops repeat "check the item, reject a duplicate ID, collect the IDs for the next step", write that once as a generic helper (`collectUniqueIds` in `web/src/lib/validateStationView.ts`, which was at 41) and give each item type a small `isValidX` predicate. A long `a && b && c` chain inside a predicate is cheap; nesting it inside loops and `if`s is what costs
- Keep the existing canvas tests that mock the 2D context; they check every draw call, so a refactor that changes the picture fails them

## Fixing an existing issue (refactoring work)

The Release 1 cleanup used this process. Behaviour must not change, so prove it with tests rather than by reading the code:
1. **Find untested branches first.** Before splitting a validator or factory, list every `raise`/`throw` in it and check that each has a test
2. **Add exact-message tests and run them on the old code.** Commit them with the refactor, but see them pass before you change anything. Match the whole message, because a partial match passes even if the refactor changes which check fires first:
   - pytest: `pytest.raises(ValueError, match=f"^{re.escape(message)}$")`
   - Vitest: `expect(fn).toThrow(new Error(message))`. Passing a string to `toThrow` only checks for a substring
   - Use `@pytest.mark.parametrize` or `it.each` with one row per error, in the order the checks run. Add a case where two inputs are wrong, to pin which error wins
3. **Keep the same checks, the same order and the same messages.** Moving a check into a helper must not move it before or after another check
4. **One issue per commit.** It keeps reviews small and gives one Refactoring Type row (Refactoring Type | Commit | Reason) per commit for the report
5. **Log any new design pattern** (for example, the lookup table of builders in `registry.py`) on the Design Patterns wiki page in the same PR, as `CLAUDE.md` requires
6. **Log the rule here.** Add the rule, what triggered it and the fix, so new code avoids it

## When the Sonar fix would be wrong

Change the code by default. Mark an issue **Accepted** only when the suggested fix would break a project rule or a test that protects one, as with S8572 on CLI handlers. Never mark a real problem as False Positive to clear the count.

When accepting:
1. Add a comment in the code giving the technical reason (the rubric requires one for every rule exception), plus a `# noqa: <ruff rule>` if ruff also flags it
2. In SonarQube: **Open → Accept**, with a comment in this form:

```
Intentional. <What the code catches or does, and why that case is expected.> <The project rule or test that the suggested fix would break, named exactly.> <Why the current code is the right call here.>
```

## Before finishing a task

- [ ] `ruff check . --extend-select PT012,PT018,A001,A002,C420,TRY400` is clean for new and changed files
- [ ] `ruff format --check .` and `pytest` pass
- [ ] No function has more than two levels of nesting inside a loop, counting closures and `useEffect` callbacks
- [ ] Every return of a function gives a tuple of the same length (no `()` on one path and `(x,)` on another)
- [ ] No string literal appears 3 or more times in a file
- [ ] Every `pytest.raises` block contains one call; its arguments are built before the block
- [ ] Every `assert` checks one condition
- [ ] Tests change globals only through `monkeypatch`
- [ ] Paths from users are resolved and checked against an allowed folder
- [ ] Functions that return a copied frozen dataclass keep its type (`_updated` helper or `cast`)
- [ ] Every `npm ci` in CI and Dockerfiles has `--ignore-scripts`
- [ ] Front end: ESLint with `eslint-plugin-sonarjs` is clean; React keys are stable IDs; no `role` where a native element exists
- [ ] After the PR scan, the SonarQube PR decoration shows 0 new issues; fix any before asking for review
