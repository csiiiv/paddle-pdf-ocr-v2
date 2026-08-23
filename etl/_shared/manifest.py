"""Reproducible run manifests and dependency fingerprints."""

from __future__ import annotations

import hashlib
import importlib.metadata
from pathlib import Path
from typing import Any

import pymupdf

from _shared.artifacts import STAGE_DIRS, write_json_atomic
from _shared.contracts import ARTIFACT_VERSION


def installed_version(distribution: str) -> str | None:
    try:
        return importlib.metadata.version(distribution)
    except importlib.metadata.PackageNotFoundError:
        return None


def sha256_file(path: Path, *, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def build_manifest(
    *,
    pdf_path: Path,
    pages: list[int],
    dpi: float,
    settings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    resolved = pdf_path.resolve()
    return {
        "artifact_version": ARTIFACT_VERSION,
        "pipeline": "paddle_pdf_ocr_v2",
        "run_layout_version": 2,
        "stage_directories": dict(STAGE_DIRS),
        "pdf": str(resolved),
        "pdf_sha256": sha256_file(resolved),
        "pages": list(pages),
        "dpi": float(dpi),
        "dependencies": {
            "pymupdf": pymupdf.__version__,
            "paddlepaddle": installed_version("paddlepaddle-gpu")
            or installed_version("paddlepaddle"),
            "paddleocr": installed_version("paddleocr"),
        },
        "settings": dict(settings or {}),
    }


def write_manifest(run_dir: Path, manifest: dict[str, Any]) -> Path:
    path = run_dir / "manifest.json"
    write_json_atomic(path, manifest)
    return path
