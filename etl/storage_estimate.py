"""Pre-run disk/storage estimates for retained ETL output artifacts.

Page count scales retained JSON under ``output/<run>/``. Estimates use average
per-page sizes from the reviewed ``extraction-smoke`` burn plus fixed
manifest/QA overhead. Free space is read from the output filesystem.
"""

from __future__ import annotations

import shutil
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

# Average retained page JSON size from extraction-smoke (bytes / page).
STAGE_PAGE_BYTES: dict[str, int] = {
    "001.00-paddle-ocr": 159_000,
    "002.00-layout": 1_500,
    "002.10-token-geometry": 110_000,
    "003.00-table-cells": 45_000,
    "004.00-extract": 211_000,
    "005.00-schema": 8_000,
}

# Fixed per-stage overhead (qa/summary.json, empty dirs, etc.).
STAGE_FIXED_BYTES: dict[str, int] = {
    "001.00-paddle-ocr": 4_000,
    "002.00-layout": 2_000,
    "002.10-token-geometry": 3_000,
    "003.00-table-cells": 2_000,
    "004.00-extract": 4_000,
    "005.00-schema": 3_000,
}

# Run-level files written beside stage dirs.
RUN_FIXED_BYTES = 8_000  # manifest.json + viewer.json + run-qa shell
RUN_QA_BYTES = 4_000

# Keep some free space on the volume after the run.
DISK_HEADROOM_BYTES = 512 * 1024 * 1024  # 512 MiB


@dataclass(frozen=True)
class StorageEstimate:
    n_pages: int
    stages: tuple[str, ...]
    bytes_per_page: int
    stage_bytes: dict[str, int]
    estimated_bytes: int
    free_bytes: int | None
    output_root: str
    headroom_bytes: int
    fits: bool | None
    notes: tuple[str, ...]
    ok_to_run: bool

    @property
    def estimated_mib(self) -> float:
        return self.estimated_bytes / (1024 * 1024)

    @property
    def free_mib(self) -> float | None:
        if self.free_bytes is None:
            return None
        return self.free_bytes / (1024 * 1024)

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["estimated_mib"] = round(self.estimated_mib, 3)
        payload["free_mib"] = None if self.free_mib is None else round(self.free_mib, 1)
        return payload


def query_free_bytes(path: Path) -> int | None:
    try:
        path.mkdir(parents=True, exist_ok=True)
        return int(shutil.disk_usage(path).free)
    except OSError:
        return None


def estimate_stage_bytes(stage: str, n_pages: int) -> int:
    page = STAGE_PAGE_BYTES.get(stage, 50_000) * n_pages
    fixed = STAGE_FIXED_BYTES.get(stage, 2_000)
    return page + fixed


def estimate_run_storage(
    *,
    pages: list[int],
    stages: list[str],
    output_root: Path,
    free_bytes: int | None = None,
) -> StorageEstimate:
    n_pages = len(pages)
    stage_bytes = {stage: estimate_stage_bytes(stage, n_pages) for stage in stages}
    total = sum(stage_bytes.values()) + RUN_FIXED_BYTES + RUN_QA_BYTES
    per_page = sum(STAGE_PAGE_BYTES.get(stage, 50_000) for stage in stages)

    if free_bytes is None:
        free_bytes = query_free_bytes(output_root)

    notes = [
        "Estimates use average page JSON sizes from output/extraction-smoke.",
        "Rasters are not retained on disk; only stage JSON + run QA/manifest.",
    ]
    fits: bool | None
    ok = True
    if free_bytes is None:
        fits = None
        notes.append("Could not read free disk space for the output volume.")
    else:
        need = total + DISK_HEADROOM_BYTES
        fits = free_bytes >= need
        if not fits:
            notes.append(
                f"Need ~{_fmt_bytes(need)} "
                f"(artifacts {_fmt_bytes(total)} + {_fmt_bytes(DISK_HEADROOM_BYTES)} headroom) "
                f"but only {_fmt_bytes(free_bytes)} is free."
            )
            ok = False

    return StorageEstimate(
        n_pages=n_pages,
        stages=tuple(stages),
        bytes_per_page=per_page,
        stage_bytes=stage_bytes,
        estimated_bytes=total,
        free_bytes=free_bytes,
        output_root=str(output_root),
        headroom_bytes=DISK_HEADROOM_BYTES,
        fits=fits,
        notes=tuple(notes),
        ok_to_run=ok,
    )


def _fmt_bytes(value: int) -> str:
    if value >= 1024 ** 3:
        return f"{value / (1024 ** 3):.2f} GiB"
    if value >= 1024 ** 2:
        return f"{value / (1024 ** 2):.1f} MiB"
    if value >= 1024:
        return f"{value / 1024:.1f} KiB"
    return f"{value} B"


def format_storage_estimate(estimate: StorageEstimate) -> str:
    fit = {True: "fits", False: "DOES NOT FIT", None: "unverified"}[estimate.fits]
    lines = [
        "Storage estimate (retained output artifacts):",
        f"  Pages: {estimate.n_pages} · stages: {', '.join(estimate.stages) or '(none)'}",
        f"  Per page: ~{_fmt_bytes(estimate.bytes_per_page)} across selected stages",
        f"  Run total: ~{_fmt_bytes(estimate.estimated_bytes)} — {fit}",
    ]
    for stage, nbytes in estimate.stage_bytes.items():
        lines.append(f"    {stage}: ~{_fmt_bytes(nbytes)}")
    if estimate.free_bytes is not None:
        lines.append(
            f"  Free on {estimate.output_root}: {_fmt_bytes(estimate.free_bytes)} "
            f"(reserves {_fmt_bytes(estimate.headroom_bytes)} headroom)"
        )
    else:
        lines.append(f"  Output root: {estimate.output_root}")
    for note in estimate.notes:
        lines.append(f"  note: {note}")
    return "\n".join(lines)
