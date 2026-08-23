#!/usr/bin/env python3
"""Stage 004.00: upstream layer JSON to canonical extract JSON and QA.

Inputs: 001.00 Paddle, 002.00 layout, optional 003.00 cells
Outputs: 004.00-extract/pages/*.json and qa/summary.json
"""

from __future__ import annotations

import argparse
from copy import deepcopy
import time
from typing import Any

from _common import add_stage_arguments, make_context, require_pass
from _shared.artifacts import read_json, write_json_atomic
from _shared.contracts import stamp_meta, validate_extract
from _shared.regions import assign_regions
from _shared.timestamps import iso_now


def merge_layers(
    *,
    page_no: int,
    paddle: dict[str, Any],
    layout: dict[str, Any],
    dpi: float,
    cells: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Assemble canonical extract without unreviewed automatic PDF patches."""
    tokens = deepcopy(paddle.get("tokens") or [])
    lines = deepcopy(paddle.get("lines") or [])
    regions = deepcopy(layout.get("regions") or [])
    assigned = assign_regions(tokens, lines, regions)
    paddle_stats = paddle.get("stats") or {}
    layout_stats = layout.get("stats") or {}
    extract = {
        "page": page_no,
        "dpi": float(dpi),
        "page_size_pt": paddle.get("page_size_pt") or layout.get("page_size_pt"),
        "image_size_px": paddle.get("image_size_px") or layout.get("image_size_px"),
        "source_mode": "paddle_primary",
        "tokens": tokens,
        "lines": lines,
        "regions": regions,
        "zones": assigned["zones"],
        "tables": deepcopy((cells or {}).get("tables") or []),
        "extract_stats": {
            "n_tokens": len(tokens),
            "n_lines": len(lines),
            "n_tokens_paddle": int(paddle_stats.get("n_tokens", len(tokens))),
            "mean_confidence": paddle_stats.get("mean_confidence"),
            "n_regions": int(layout_stats.get("n_regions", len(regions))),
            "n_chrome_regions": int(layout_stats.get("n_chrome", 0)),
            "n_table_regions": int(layout_stats.get("n_table", 0)),
            "n_text_regions": int(layout_stats.get("n_text", 0)),
            "n_zones": len(assigned["zones"]),
            "n_chrome_tokens": assigned["n_chrome_tokens"],
            "n_unassigned_tokens": assigned["n_unassigned_tokens"],
            "n_active_tokens": len(tokens) - assigned["n_chrome_tokens"],
            "n_cell_tables": int((cells or {}).get("stats", {}).get("n_tables", 0)),
            "n_cells": int((cells or {}).get("stats", {}).get("n_cells", 0)),
            "n_ok_tables": int((cells or {}).get("stats", {}).get("n_ok", 0)),
        },
    }
    stamp_meta(extract, stage="extract", producer="paddle_first_merge_v1")
    validate_extract(extract)
    return extract


def run_stage(context) -> dict[str, Any]:
    results = []
    started_at, started = iso_now(), time.perf_counter()
    for page_no in context.pages:
        page_started_at, page_started = iso_now(), time.perf_counter()
        try:
            paddle = read_json(context.store.layer_path("paddle", page_no))
            layout = read_json(context.store.layer_path("layout", page_no))
            cells_path = context.store.layer_path("cells", page_no)
            cells = read_json(cells_path) if cells_path.is_file() else None
            extract = merge_layers(page_no=page_no, paddle=paddle, layout=layout,
                                   dpi=context.dpi, cells=cells)
            write_json_atomic(context.store.extract_path(page_no), extract)
            result = {"page": page_no, "pass": True, **extract["extract_stats"]}
        except Exception as error:
            result = {"page": page_no, "pass": False,
                      "error_type": type(error).__name__, "error": str(error)}
        result.update({"started_at": page_started_at, "completed_at": iso_now(),
                       "timestamp_source": "captured",
                       "elapsed_s": round(time.perf_counter() - page_started, 3)})
        results.append(result)
    n_fail = sum(not result["pass"] for result in results)
    summary = {"artifact_version": 1, "gate": "ASSEMBLE_EXTRACT",
        "name": "paddle_first_extract", "n_pages": len(results), "n_fail": n_fail,
        "started_at": started_at, "completed_at": iso_now(),
        "timestamp_source": "captured", "elapsed_s": round(time.perf_counter() - started, 3),
        "pages": results, "pass": n_fail == 0}
    write_json_atomic(context.store.stage_qa_path("extract"), summary)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    add_stage_arguments(parser)
    context = make_context(parser.parse_args())
    summary = run_stage(context)
    print(f"004.00 Extract: pages={summary['n_pages']} fail={summary['n_fail']} elapsed={summary['elapsed_s']}s")
    require_pass(summary)


if __name__ == "__main__":
    main()
