#!/usr/bin/env python3
"""Archived comparison stage: PDF pages to model layout-region proposals.

This script is not registered in the canonical ACTIVE_STAGES sequence.

Inputs: source PDF pages
Outputs: 002.00-layout/pages/*.json and qa/summary.json
"""

from __future__ import annotations

import argparse
import time
from typing import Any

import numpy as np
import pymupdf

from _common import add_stage_arguments, make_context, require_pass
from _shared.artifacts import write_json_atomic
from _shared.contracts import stamp_meta
from _shared.raster import render_page_rgb
from _shared.regions import assign_regions, best_region
from _shared.timestamps import iso_now

CHROME_LABELS = frozenset({"header", "footer", "header_image", "footer_image", "number", "footnote", "aside_text", "seal"})
LABEL_PRIORITY = {
    "table": 0, "text": 1, "content": 1, "paragraph_title": 2,
    "figure_title": 2, "doc_title": 2, "formula": 3, "chart": 3,
    "image": 4, "header": 5, "footer": 5, "number": 5,
    "footnote": 5, "aside_text": 5,
}


def build_layout(*, device: str = "gpu:0") -> Any:
    from paddleocr import LayoutDetection
    try:
        return LayoutDetection(device=device)
    except TypeError:
        return LayoutDetection()


def _get(payload: Any, key: str, default: Any = None) -> Any:
    if isinstance(payload, dict):
        return payload.get(key, default)
    if hasattr(payload, "get"):
        try:
            return payload.get(key, default)
        except Exception:  # Paddle Result mappings vary by patch release
            pass
    try:
        return payload[key]
    except (KeyError, TypeError, IndexError):
        return default


def _payload_keys(payload: Any) -> list[str]:
    try:
        return sorted(str(key) for key in payload.keys())
    except (AttributeError, TypeError):
        return []


def parse_layout_result(raw: Any, *, dpi: float, score_thresh: float = 0.4) -> dict[str, Any]:
    if dpi <= 0:
        raise ValueError(f"dpi must be positive: {dpi}")
    if not 0 <= score_thresh <= 1:
        raise ValueError(f"score_thresh must be in [0, 1]: {score_thresh}")
    item = raw[0] if isinstance(raw, list) and raw else raw
    boxes = _get(item, "boxes")
    if boxes is None:
        boxes = []
    scale = 72.0 / dpi
    regions: list[dict[str, Any]] = []
    n_below_threshold = 0
    n_invalid = 0
    for box in boxes:
        label = str(_get(box, "label") or _get(box, "cls_label") or "unknown")
        score = float(_get(box, "score") or 0.0)
        if score < score_thresh:
            n_below_threshold += 1
            continue
        coord = _get(box, "coordinate")
        if coord is None:
            coord = _get(box, "bbox")
        array = np.asarray(coord, dtype=float) if coord is not None else np.array([])
        if array.size != 4:
            n_invalid += 1
            continue
        x0, y0, x1, y1 = array.reshape(-1).tolist()
        regions.append({
            "region_id": 0, "label": label, "score": round(score, 4),
            "bbox": [round(min(x0, x1) * scale, 2), round(min(y0, y1) * scale, 2), round(max(x0, x1) * scale, 2), round(max(y0, y1) * scale, 2)],
            "chrome": label in CHROME_LABELS,
        })
    regions.sort(key=lambda region: (region["bbox"][1], region["bbox"][0]))
    for region_id, region in enumerate(regions):
        region["region_id"] = region_id
    return {
        "regions": regions,
        "stats": {
            "n_regions": len(regions),
            "n_chrome": sum(region["chrome"] for region in regions),
            "n_table": sum(region["label"] == "table" for region in regions),
            "n_text": sum(region["label"] in {"text", "content"} for region in regions),
        },
        "diagnostics": {
            "raw_type": type(raw).__name__, "raw_keys": _payload_keys(item),
            "score_thresh": score_thresh, "n_below_threshold": n_below_threshold,
            "n_invalid_boxes": n_invalid,
        },
    }


def extract_layout(image_rgb: np.ndarray, *, dpi: float, engine: Any, score_thresh: float = 0.4) -> dict[str, Any]:
    image_bgr = image_rgb[:, :, ::-1].copy()
    return parse_layout_result(engine.predict(image_bgr), dpi=dpi, score_thresh=score_thresh)


def run_stage(context, *, engine: Any | None = None) -> dict[str, Any]:
    results = []
    started_at, started = iso_now(), time.perf_counter()
    engine = engine or build_layout(device=context.device)
    with pymupdf.open(context.pdf) as document:
        for page_no in context.pages:
            page_started_at, page_started = iso_now(), time.perf_counter()
            try:
                if not 1 <= page_no <= document.page_count:
                    raise ValueError(f"page {page_no} outside PDF range 1..{document.page_count}")
                image, page_size = render_page_rgb(document[page_no - 1], dpi=context.dpi)
                payload = extract_layout(image, dpi=context.dpi, engine=engine,
                                         score_thresh=context.layout_score)
                payload.update({"page": page_no,
                    "page_size_pt": [round(value, 2) for value in page_size],
                    "image_size_px": [int(image.shape[1]), int(image.shape[0])]})
                stamp_meta(payload, stage="layer:layout", producer="LayoutDetection")
                write_json_atomic(context.store.layer_path("layout", page_no), payload)
                result = {"page": page_no, "pass": True, **payload["stats"], **payload["diagnostics"]}
            except Exception as error:
                result = {"page": page_no, "pass": False,
                          "error_type": type(error).__name__, "error": str(error)}
            result.update({"started_at": page_started_at, "completed_at": iso_now(),
                           "timestamp_source": "captured",
                           "elapsed_s": round(time.perf_counter() - page_started, 3)})
            results.append(result)
    n_fail = sum(not result["pass"] for result in results)
    summary = {"artifact_version": 1, "gate": "EXTRACT_LAYOUT",
        "name": "layout_region_layer", "n_pages": len(results), "n_fail": n_fail,
        "started_at": started_at, "completed_at": iso_now(),
        "timestamp_source": "captured", "elapsed_s": round(time.perf_counter() - started, 3),
        "settings": {"dpi": context.dpi, "device": context.device,
                     "score_thresh": context.layout_score},
        "pages": results, "pass": n_fail == 0}
    write_json_atomic(context.store.stage_qa_path("layout"), summary)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    add_stage_arguments(parser, gpu=True, layout_score=True)
    context = make_context(parser.parse_args())
    summary = run_stage(context)
    print(f"002.00 Layout: pages={summary['n_pages']} fail={summary['n_fail']} elapsed={summary['elapsed_s']}s")
    require_pass(summary)


if __name__ == "__main__":
    main()
