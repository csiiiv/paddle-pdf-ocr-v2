"""Canonical run layout and transactional JSON persistence."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

LayerName = Literal["paddle", "layout", "cells"]
StageName = Literal[
    "foundation", "paddle", "layout", "cells", "extract", "schema",
    "rows", "domain", "hierarchy", "collation",
]

STAGE_DIRS: dict[StageName, str] = {
    "foundation": "000.00-foundation",
    "paddle": "001.00-paddle-ocr",
    "layout": "002.00-layout",
    "cells": "003.00-table-cells",
    "extract": "004.00-extract",
    "schema": "005.00-schema",
    "rows": "006.00-rows",
    "domain": "007.00-domain",
    "hierarchy": "008.00-hierarchy",
    "collation": "009.00-collation",
}


@dataclass(frozen=True)
class ArtifactStore:
    """Own every path convention for a single run."""

    root: Path

    def stage_root(self, stage: StageName) -> Path:
        return self.root / STAGE_DIRS[stage]

    def layer_path(self, layer: LayerName, page_no: int) -> Path:
        return self.stage_root(layer) / "pages" / f"page-{page_no:04d}.json"

    def extract_path(self, page_no: int) -> Path:
        return self.stage_root("extract") / "pages" / f"page-{page_no:04d}.json"

    def structured_path(self, page_no: int) -> Path:
        return self.stage_root("hierarchy") / "pages" / f"page-{page_no:04d}.json"

    def rows_path(self, page_no: int) -> Path:
        """Canonical pre-hierarchy rows for engine-independent inspection."""
        return self.stage_root("rows") / "pages" / f"page-{page_no:04d}.json"

    def stage_qa_path(self, stage: StageName, name: str = "summary.json") -> Path:
        if not name or Path(name).name != name or not name.endswith(".json"):
            raise ValueError(f"QA artifact must be a JSON filename: {name!r}")
        return self.stage_root(stage) / "qa" / name

    def run_qa_path(self, name: str) -> Path:
        """Cross-stage comparisons only; stage QA belongs beside its stage."""
        if not name or Path(name).name != name or not name.endswith(".json"):
            raise ValueError(f"QA artifact must be a JSON filename: {name!r}")
        return self.root / "999.00-run-qa" / name

    def discover_pages(
        self, stage: Literal["extract", "rows", "hierarchy"] = "extract"
    ) -> list[int]:
        folder = self.stage_root(stage) / "pages"
        pages: list[int] = []
        for path in sorted(folder.glob("page-*.json")):
            try:
                pages.append(int(path.stem.removeprefix("page-")))
            except ValueError:
                continue
        return pages


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object in {path}")
    return value


def write_json_atomic(path: Path, value: dict[str, Any]) -> None:
    """Write complete JSON beside the target, then atomically replace it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp_path, path)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise
