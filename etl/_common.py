"""Shared CLI/bootstrap utilities for numbered ETL stage executables."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PROJECT = Path(__file__).resolve().parents[1]
REPO = PROJECT.parent
from _shared.artifacts import STAGE_DIRS, ArtifactStore, write_json_atomic
from _shared.manifest import build_manifest, write_manifest


@dataclass(frozen=True)
class StageContext:
    pdf: Path
    run_dir: Path
    pages: list[int]
    dpi: float
    device: str
    layout_score: float
    cells_score: float

    @property
    def store(self) -> ArtifactStore:
        return ArtifactStore(self.run_dir)


def resolve_pdf(path: Path) -> Path:
    """Resolve absolute, project-local, then parent-workspace PDF paths."""
    if path.is_absolute():
        return path
    project_candidate = PROJECT / path
    if project_candidate.is_file():
        return project_candidate
    parent_candidate = REPO / path
    if parent_candidate.is_file():
        return parent_candidate
    return project_candidate


def resolve_project_path(path: Path) -> Path:
    """Resolve a project-relative path (fixtures, configs) against PROJECT."""
    if path.is_absolute():
        return path
    return PROJECT / path


def parse_pages(spec: str) -> list[int]:
    pages: set[int] = set()
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            start, end = (int(value) for value in part.split("-", 1))
            if end < start:
                raise ValueError(f"descending page range: {part}")
            pages.update(range(start, end + 1))
        else:
            pages.add(int(part))
    if not pages or min(pages) < 1:
        raise ValueError(f"invalid page selection: {spec!r}")
    return sorted(pages)


def _collect_page_values(value: Any, *, path: str) -> set[int]:
    pages: set[int] = set()
    if isinstance(value, int):
        pages.add(value)
    elif isinstance(value, str):
        pages.update(parse_pages(value))
    elif isinstance(value, dict):
        if "page" in value:
            pages.add(int(value["page"]))
        elif "pages" in value:
            pages.update(_collect_page_values(value["pages"], path=f"{path}.pages"))
        else:
            raise ValueError(
                f"{path}: object needs 'page' or 'pages' (keys: {sorted(value)})"
            )
    elif isinstance(value, list):
        if not value:
            raise ValueError(f"{path}: empty page list")
        for index, item in enumerate(value):
            pages.update(_collect_page_values(item, path=f"{path}[{index}]"))
    else:
        raise ValueError(f"{path}: unsupported page value type {type(value).__name__}")
    return pages


def load_pages_from_json(path: Path, obj_name: str) -> list[int]:
    """Load a named page set from JSON (e.g. migration_gold edge_pages)."""
    resolved = resolve_project_path(path)
    if not resolved.is_file():
        raise ValueError(f"pages JSON not found: {resolved}")
    payload = json.loads(resolved.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{resolved}: top-level JSON must be an object")
    if obj_name not in payload:
        keys = ", ".join(sorted(map(str, payload))) or "(none)"
        raise ValueError(
            f"pages object {obj_name!r} not in {resolved}; available: {keys}"
        )
    pages = _collect_page_values(payload[obj_name], path=obj_name)
    if not pages or min(pages) < 1:
        raise ValueError(f"invalid page selection from {obj_name!r} in {resolved}")
    return sorted(pages)


def add_stage_arguments(
    parser: argparse.ArgumentParser,
    *,
    gpu: bool = False,
    layout_score: bool = False,
    cells_score: bool = False,
) -> None:
    parser.add_argument("--pdf", type=Path, required=True)
    parser.add_argument("--pages", required=True)
    parser.add_argument("--run", required=True)
    parser.add_argument("--dpi", type=float, default=200.0)
    if gpu:
        parser.add_argument("--device", default="gpu:0")
    if layout_score:
        parser.add_argument("--layout-score", type=float, default=0.4)
    if cells_score:
        parser.add_argument("--cells-score", type=float, default=0.3)


def make_context(args: argparse.Namespace, *, paddle_lang: str = "en") -> StageContext:
    try:
        pages = parse_pages(args.pages)
    except ValueError as error:
        raise SystemExit(str(error)) from error
    pdf = resolve_pdf(args.pdf)
    if Path(args.run).name != args.run:
        raise SystemExit("--run must be one folder name")
    context = StageContext(
        pdf=pdf, run_dir=PROJECT / "output" / args.run, pages=pages,
        dpi=args.dpi, device=getattr(args, "device", "gpu:0"),
        layout_score=getattr(args, "layout_score", 0.4),
        cells_score=getattr(args, "cells_score", 0.3),
    )
    manifest = build_manifest(
        pdf_path=context.pdf, pages=context.pages, dpi=context.dpi,
        settings={"paddle": {"lang": paddle_lang, "device": context.device,
                  "return_word_box": True},
                  "layout": {"score_thresh": context.layout_score},
                  "cells": {"score_thresh": context.cells_score}},
    )
    write_manifest(context.run_dir, manifest)
    write_json_atomic(context.run_dir / "viewer.json", {
        "artifact_version": 1, "run": context.run_dir.name,
        "pdf": manifest["pdf"], "pages": context.pages, "dpi": context.dpi,
        "run_layout_version": manifest["run_layout_version"],
        "stage_directories": dict(STAGE_DIRS),
    })
    return context


def require_pass(summary: dict) -> None:
    if not summary["pass"]:
        raise SystemExit(1)
