---
name: sonar-clean-code
description: Use when writing, changing or reviewing TransitSync code (Python simulator, scripts and API, pytest tests, TypeScript/React front end, CI workflows) so new code does not add SonarQube Cloud issues. Lists every rule the project has been flagged for, the pattern that triggers it, the fix, and the local check that catches it before a push.
---

# Keep new code SonarQube clean (TransitSync)

SonarQube Cloud scans every PR (`team-exception-handlers_TransitSync`). Iteration target: **0 high issues, at most 30 medium**, and no new issues in any PR. This skill lists the rules the project has already hit, what triggers each one, and how to write code that does not trigger it. It sits alongside `code-workflow` (rubric) and `python-tests` (test design). If anything here conflicts with `CLAUDE.md`, `CLAUDE.md` wins.

Snapshot on 2026-10-31: 68 open issues. 49 are S5778 and 13 are S9073, all in tests. Fixed or accepted so far: S3776 (8), S8572 (4), S8707 (2), S7519 (2), S8544 (1).

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

For the front end, add `eslint-plugin-sonarjs` (recommended config) to the `web/` ESLint setup so the TypeScript rules below show in the editor.

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
This was the most common critical issue (8 fixed). Sonar adds 1 for each `if`, `elif`, `else`, loop, `except`, ternary and run of `and`/`or`, plus 1 more for every level the structure is nested. A check inside a loop inside another loop is expensive.
- Keep at most two levels of nesting inside a loop. When a third appears, move the inner block into a helper
- Validate one item per helper: the loop collects, the helper checks (`_service_window`, `_check_platform_stop`, `_check_stop_time`, `_mapping_platform` in `scripts/`)
- Replace `if kind == A ... elif kind == B ...` chains with a lookup table of small functions (`_FIELD_CHECKS` in `simulator/engine/events.py`)
- Use guard clauses (`if bad: raise`) instead of wrapping the rest of the function in `if`/`else`
- Never repeat a loop that already exists elsewhere; share one helper (`_check_chronological` in `simulator/trains/train.py`)
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

### S7519: `dict.fromkeys` for a constant value
`{key: 0 for key in keys}` becomes `dict.fromkeys(keys, 0)`. Only for immutable values: `dict.fromkeys(keys, [])` shares one list between every key, so keep the comprehension for lists, sets and dicts.

## CI and dependencies

### S8544: install only locked versions
- Python: every package pinned with `==` in `requirements.txt` / `requirements-dev.txt`
- Front end: commit `package-lock.json` and install with `npm ci`, never `npm install`, in CI
- Pin GitHub Actions to a release tag (`actions/setup-node@v4`), never a branch

## TypeScript and React (front end starting in Iteration 3)

No front-end issues exist yet. These are the rules Sonar most often raises on React code; write to them from the first commit.

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
- [ ] No function has more than two levels of nesting inside a loop
- [ ] Every `pytest.raises` block contains one call; its arguments are built before the block
- [ ] Every `assert` checks one condition
- [ ] Tests change globals only through `monkeypatch`
- [ ] Paths from users are resolved and checked against an allowed folder
- [ ] Front end: ESLint with `eslint-plugin-sonarjs` is clean; React keys are stable IDs
- [ ] After the PR scan, the SonarQube PR decoration shows 0 new issues; fix any before asking for review
