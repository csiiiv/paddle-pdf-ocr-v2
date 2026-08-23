"""Timestamp conventions for retained records and QA artifacts."""

from __future__ import annotations

from datetime import datetime


def iso_now() -> str:
    """Return local ISO 8601 time with timezone and second precision."""
    return datetime.now().astimezone().isoformat(timespec="seconds")

