"""Versioned boundary contracts for pipeline artifacts."""

from __future__ import annotations

from typing import Any

ARTIFACT_VERSION = 1
EXTRACT_REQUIRED = frozenset({"page", "tokens", "lines", "regions", "zones"})


class ContractError(ValueError):
    """An artifact does not satisfy its declared boundary."""


def validate_extract(data: dict[str, Any]) -> None:
    """Validate the minimum canonical extract consumed by structure stages."""
    missing = sorted(EXTRACT_REQUIRED.difference(data))
    if missing:
        raise ContractError(f"extract missing required fields: {missing}")
    page = data.get("page")
    if not isinstance(page, int) or isinstance(page, bool) or page < 1:
        raise ContractError(f"extract page must be a positive integer: {page!r}")
    for field in ("tokens", "lines", "regions", "zones"):
        if not isinstance(data.get(field), list):
            raise ContractError(f"extract {field} must be a list")


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
