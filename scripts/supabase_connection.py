# AI contribution: 50% or more AI-generated
"""Shared verified, read-only Supabase connection for offline extraction."""

import os
from collections.abc import Iterator
from contextlib import contextmanager

import psycopg
from psycopg.rows import dict_row


@contextmanager
def read_only_connection() -> Iterator[psycopg.Connection]:
    """Open one snapshot; let the caller sanitize operation-specific errors."""
    url = os.environ.get("SUPABASE_DB_URL")
    if not url or not url.strip():
        raise ValueError("Set SUPABASE_DB_URL in the process environment first")
    with psycopg.connect(
        url,
        row_factory=dict_row,
        connect_timeout=10,
        sslmode="verify-full",
        sslrootcert=os.environ.get("SUPABASE_SSL_ROOT_CERT") or "system",
        prepare_threshold=None,
    ) as connection:
        connection.read_only = True
        connection.isolation_level = psycopg.IsolationLevel.REPEATABLE_READ
        yield connection
