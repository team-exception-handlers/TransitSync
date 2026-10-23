# AI contribution: 50% or more AI-generated
"""Shared stderr logging configuration for offline extraction commands."""

import logging


def configure_logging() -> None:
    """Configure CLI diagnostics without changing an embedding application's setup."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )
