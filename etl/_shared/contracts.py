"""Versioned boundary contracts for pipeline artifacts."""

from __future__ import annotations

from typing import Any

ARTIFACT_VERSION = 1
EXTRACT_REQUIRED = frozenset({"page", "tokens", "lines", "regions", "zones"})
SCHEMA_MODES = frozenset({"lattice", "amount_anchored", "years", "prose", "passthrough"})


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


def validate_schema(data: dict[str, Any]) -> None:
    """Validate page schema decisions consumed by canonical row assembly."""
    page = data.get("page")
    if not isinstance(page, int) or isinstance(page, bool) or page < 1:
        raise ContractError(f"schema page must be a positive integer: {page!r}")
    if data.get("schema_mode") not in SCHEMA_MODES:
        raise ContractError(f"invalid page schema_mode: {data.get('schema_mode')!r}")
    decisions = data.get("zone_schemas")
    if not isinstance(decisions, list) or not decisions:
        raise ContractError("schema zone_schemas must be a non-empty list")
    for index, decision in enumerate(decisions):
        if decision.get("schema_mode") not in SCHEMA_MODES:
            raise ContractError(f"zone_schemas[{index}] has invalid schema_mode")
        if decision.get("qa_status") not in {"accept", "review", "reject"}:
            raise ContractError(f"zone_schemas[{index}] has invalid qa_status")
        confidence = decision.get("confidence")
        if not isinstance(confidence, (int, float)) or isinstance(confidence, bool) or not 0 <= confidence <= 1:
            raise ContractError(f"zone_schemas[{index}] has invalid confidence")


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
