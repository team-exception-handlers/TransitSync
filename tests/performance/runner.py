# AI contribution: 50% or more AI-generated
"""Bound opt-in benchmarks without presenting timeouts as completion times.

The worker budget includes process startup; returned API timings do not.
Slow and failed experiments remain failures of the opt-in test suite.
"""

import multiprocessing

import pytest

from scripts.benchmark_simulation import measure


def _worker(connection, strategy, options):
    """Send a completed measurement or an explicit execution failure."""
    try:
        connection.send(("ok", measure(strategy, **options)))
    except Exception as error:
        connection.send(("error", f"{type(error).__name__}: {error}"))
    finally:
        connection.close()


def measured(strategy, timeout_s, **options):
    """Measure inside a fresh process; exclude spawning from API timings.

    A timed-out run fails with an unfinished status, never a fabricated timing.
    Terminating its process also releases large full-day audit allocations.
    """
    context = multiprocessing.get_context("spawn")
    receive, send = context.Pipe(duplex=False)
    process = context.Process(target=_worker, args=(send, strategy, options))
    try:
        process.start()
        send.close()
        if not receive.poll(timeout_s):
            print(
                f"{strategy}: UNFINISHED within {timeout_s:g} s worker budget",
                flush=True,
            )
            pytest.fail("Benchmark timed out; API completion time is unknown")
        try:
            status, result = receive.recv()
        except EOFError:
            pytest.fail("Benchmark worker exited without returning a measurement")
        if status != "ok":
            pytest.fail(result)
        return result
    finally:
        if process.is_alive():
            process.terminate()
        process.join()
        receive.close()
        send.close()
