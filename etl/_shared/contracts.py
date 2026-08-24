"""Versioned boundary contracts for pipeline artifacts."""

from __future__ import annotations

ARTIFACT_VERSION = 1
from typing import Any


def stamp_meta(data: dict[str, Any], *, stage: str, producer: str) -> dict[str, Any]:
    """Attach artifact provenance without replacing stage-specific metadata."""
    meta = data.setdefault("artifact", {})
    meta.update(
        {
            "version": ARTIFACT_VERSION,
            "stage": stage,
            "producer": producer,
        }
    )
    return data
