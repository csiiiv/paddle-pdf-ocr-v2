#!/usr/bin/env python3
"""Stage 003.00: upstream OCR/layout JSON to optional table-cell JSON.

Inputs: 001.00 Paddle, 002.00 layout, and source PDF pages
Outputs: 003.00-table-cells/pages/*.json and qa/summary.json
"""

from __future__ import annotations

import argparse
from copy import deepcopy
import time
from typing import Any

import numpy as np
import pymupdf

from _common import add_stage_arguments, make_context, require_pass
from _shared.artifacts import read_json, write_json_atomic
from _shared.contracts import stamp_meta
from _shared.raster import render_page_rgb
from _shared.regions import assign_regions
from _shared.timestamps import iso_now

WIRED_MODEL = "RT-DETR-L_wired_table_cell_det"
WIRELESS_MODEL = "RT-DETR-L_wireless_table_cell_det"


def build_cells(*, device: str = "gpu:0", wireless: bool = False) -> Any:
    from paddleocr import TableCellsDetection
    model = WIRELESS_MODEL if wireless else WIRED_MODEL
    try:
        return TableCellsDetection(model_name=model, device=device)
    except TypeError:
        return TableCellsDetection(model_name=model)


def _get(payload: Any, key: str, default: Any = None) -> Any:
    if isinstance(payload, dict):
        return payload.get(key, default)
    if hasattr(payload, "get"):
        try:
            return payload.get(key, default)
        except Exception:
            pass
    try:
        return payload[key]
    except (KeyError, TypeError, IndexError):
        return default


def parse_cell_result(raw: Any, *, score_thresh: float = 0.3) -> list[tuple[list[float], float]]:
    item = raw[0] if isinstance(raw, list) and raw else raw
    boxes = _get(item, "boxes")
    if boxes is None:
        boxes = []
    parsed = []
    for box in boxes:
        score = float(_get(box, "score") or 0.0)
        coordinate = _get(box, "coordinate")
        if coordinate is None:
            coordinate = _get(box, "bbox")
        array = np.asarray(coordinate, dtype=float) if coordinate is not None else np.array([])
        if score >= score_thresh and array.size == 4:
            parsed.append((array.reshape(-1).tolist(), score))
    return parsed


def _clusters(values: list[float], tolerance: float) -> list[float]:
    groups: list[list[float]] = []
    for value in sorted(values):
        # Preserve the proven single-link clustering: slowly shifting cell
        # centers remain one structural column when adjacent detections agree.
        if not groups or value - groups[-1][-1] > tolerance:
            groups.append([value])
        else:
            groups[-1].append(value)
    return [sum(group) / len(group) for group in groups]


def _mid_x(box: list[float]) -> float:
    return (box[0] + box[2]) / 2


def _mid_y(box: list[float]) -> float:
    return (box[1] + box[3]) / 2


def assign_grid(cells: list[dict[str, Any]]) -> tuple[int, int]:
    if not cells:
        return 0, 0
    rows = _clusters([_mid_y(cell["bbox"]) for cell in cells], 8.0)
    columns = _clusters([_mid_x(cell["bbox"]) for cell in cells], 18.0)
    for cell in cells:
        cell["row"] = min(range(len(rows)), key=lambda i: abs(_mid_y(cell["bbox"]) - rows[i]))
        cell["col"] = min(range(len(columns)), key=lambda i: abs(_mid_x(cell["bbox"]) - columns[i]))
        cell["text"] = ""
        cell["token_ids"] = []
    cells.sort(key=lambda cell: (cell["row"], cell["col"], cell["bbox"][0]))
    return len(rows), len(columns)


def fill_cell_text(cells: list[dict[str, Any]], tokens: list[dict[str, Any]], lines: list[dict[str, Any]]) -> None:
    for cell in cells:
        box = cell["bbox"]
        token_ids = [
            index for index, token in enumerate(tokens)
            if not token.get("chrome") and token.get("bbox")
            and box[0] <= _mid_x(token["bbox"]) <= box[2]
            and box[1] <= _mid_y(token["bbox"]) <= box[3]
        ]
        parts = []
        min_area = 0.05 * max(box[2] - box[0], 1.0) * max(box[3] - box[1], 1.0)
        for line in lines:
            line_box = line.get("bbox")
            if not line_box or line.get("chrome"):
                continue
            x_overlap = max(0.0, min(box[2], line_box[2]) - max(box[0], line_box[0]))
            y_overlap = max(0.0, min(box[3], line_box[3]) - max(box[1], line_box[1]))
            center_inside = box[0] <= _mid_x(line_box) <= box[2] and box[1] <= _mid_y(line_box) <= box[3]
            text = str(line.get("text") or "").strip()
            if text and (center_inside or x_overlap * y_overlap >= min_area):
                parts.append((line_box[1], line_box[0], text))
        parts.sort()
        unique = []
        for _, _, text in parts:
            if not unique or unique[-1] != text:
                unique.append(text)
        if unique:
            text = " ".join(unique)
        else:
            ordered = sorted(token_ids, key=lambda i: (tokens[i]["bbox"][1], tokens[i]["bbox"][0]))
            text = " ".join(str(tokens[i].get("text") or "") for i in ordered)
        cell["text"] = " ".join(text.split())
        cell["token_ids"] = token_ids


def _empty(region: dict[str, Any], reason: str, model: str | None = None) -> dict[str, Any]:
    return {
        "table_id": 0, "region_id": region.get("region_id"),
        "bbox": list(region.get("bbox") or []), "cells": [],
        "n_rows": 0, "n_cols": 0, "fill_ratio": 0.0,
        "ok": False, "model": model, "reason": reason,
    }


def detect_cells(
    image_rgb: np.ndarray,
    *, dpi: float,
    regions: list[dict[str, Any]],
    tokens: list[dict[str, Any]],
    lines: list[dict[str, Any]],
    wired_engine: Any,
    wireless_engine: Any | None = None,
    score_thresh: float = 0.3,
) -> dict[str, Any]:
    image_bgr = image_rgb[:, :, ::-1].copy()
    table_regions = [region for region in regions if region.get("label") == "table" and not region.get("chrome")]
    tables = []
    scale = dpi / 72.0
    for region in table_regions:
        started_model = WIRED_MODEL
        x0 = max(0, int((region["bbox"][0] - 4.0) * scale))
        y0 = max(0, int((region["bbox"][1] - 4.0) * scale))
        x1 = min(image_bgr.shape[1], int((region["bbox"][2] + 4.0) * scale))
        y1 = min(image_bgr.shape[0], int((region["bbox"][3] + 4.0) * scale))
        crop = image_bgr[y0:y1, x0:x1].copy()
        if crop.shape[0] < 16 or crop.shape[1] < 16:
            tables.append(_empty(region, "crop_too_small"))
            continue
        try:
            boxes = parse_cell_result(wired_engine.predict(crop), score_thresh=score_thresh)
            if len(boxes) < 4 and wireless_engine is not None:
                wireless = parse_cell_result(wireless_engine.predict(crop), score_thresh=score_thresh)
                if len(wireless) > len(boxes):
                    boxes = wireless
                    started_model = WIRELESS_MODEL
            if not boxes:
                tables.append(_empty(region, "no_cells", started_model))
                continue
            cells = []
            for cell_id, (coordinate, score) in enumerate(boxes):
                bx0, by0, bx1, by1 = coordinate
                cells.append({
                    "cell_id": cell_id,
                    "bbox": [round((bx0 + x0) / scale, 2), round((by0 + y0) / scale, 2), round((bx1 + x0) / scale, 2), round((by1 + y0) / scale, 2)],
                    "score": round(score, 4),
                })
            n_rows, n_cols = assign_grid(cells)
            fill_cell_text(cells, tokens, lines)
            occupancy = len({(cell["row"], cell["col"]) for cell in cells})
            fill_ratio = occupancy / max(n_rows * n_cols, 1)
            ok = n_rows >= 3 and n_cols >= 2 and fill_ratio >= 0.15
            tables.append({
                "table_id": 0, "region_id": region.get("region_id"),
                "bbox": list(region["bbox"]), "cells": cells,
                "n_rows": n_rows, "n_cols": n_cols,
                "fill_ratio": round(fill_ratio, 3), "ok": ok,
                "model": started_model, "reason": None if ok else "weak_grid",
            })
        except Exception as error:
            tables.append(_empty(region, f"exception:{type(error).__name__}:{error}", started_model))
    for table_id, table in enumerate(tables):
        table["table_id"] = table_id
    return {
        "tables": tables,
        "stats": {
            "n_tables": len(tables),
            "n_cells": sum(len(table["cells"]) for table in tables),
            "n_ok": sum(bool(table["ok"]) for table in tables),
            "n_weak": sum(not table["ok"] for table in tables),
        },
        "diagnostics": {"score_thresh": score_thresh, "wireless_available": wireless_engine is not None},
    }


def run_stage(context, *, wired_engine: Any | None = None,
              wireless_engine: Any | None = None) -> dict[str, Any]:
    results = []
    started_at, started = iso_now(), time.perf_counter()
    wired_engine = wired_engine or build_cells(device=context.device, wireless=False)
    if wireless_engine is None:
        try:
            wireless_engine = build_cells(device=context.device, wireless=True)
        except Exception:
            wireless_engine = None
    with pymupdf.open(context.pdf) as document:
        for page_no in context.pages:
            page_started_at, page_started = iso_now(), time.perf_counter()
            try:
                paddle = read_json(context.store.layer_path("paddle", page_no))
                layout = read_json(context.store.layer_path("layout", page_no))
                tokens, lines = deepcopy(paddle.get("tokens") or []), deepcopy(paddle.get("lines") or [])
                assign_regions(tokens, lines, deepcopy(layout.get("regions") or []))
                image, page_size = render_page_rgb(document[page_no - 1], dpi=context.dpi)
                payload = detect_cells(image, dpi=context.dpi,
                    regions=layout.get("regions") or [], tokens=tokens, lines=lines,
                    wired_engine=wired_engine, wireless_engine=wireless_engine,
                    score_thresh=context.cells_score)
                payload.update({"page": page_no,
                    "page_size_pt": [round(value, 2) for value in page_size],
                    "image_size_px": [int(image.shape[1]), int(image.shape[0])]})
                stamp_meta(payload, stage="layer:cells", producer="TableCellsDetection")
                write_json_atomic(context.store.layer_path("cells", page_no), payload)
                models = sorted({table["model"] for table in payload["tables"] if table.get("model")})
                result = {"page": page_no, "pass": True, **payload["stats"],
                          "models_used": models, **payload["diagnostics"]}
            except Exception as error:
                result = {"page": page_no, "pass": False,
                          "error_type": type(error).__name__, "error": str(error)}
            result.update({"started_at": page_started_at, "completed_at": iso_now(),
                           "timestamp_source": "captured",
                           "elapsed_s": round(time.perf_counter() - page_started, 3)})
            results.append(result)
    n_fail = sum(not result["pass"] for result in results)
    summary = {"artifact_version": 1, "gate": "EXTRACT_CELLS",
        "name": "selective_table_cells", "selective": True,
        "n_pages": len(results), "n_fail": n_fail,
        "n_ok": sum(result.get("n_ok", 0) for result in results),
        "n_weak": sum(result.get("n_weak", 0) for result in results),
        "started_at": started_at, "completed_at": iso_now(),
        "timestamp_source": "captured", "elapsed_s": round(time.perf_counter() - started, 3),
        "settings": {"dpi": context.dpi, "device": context.device,
                     "score_thresh": context.cells_score},
        "pages": results, "pass": n_fail == 0}
    write_json_atomic(context.store.stage_qa_path("cells"), summary)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    add_stage_arguments(parser, gpu=True, cells_score=True)
    context = make_context(parser.parse_args())
    summary = run_stage(context)
    print(f"003.00 Cells: pages={summary['n_pages']} fail={summary['n_fail']} ok={summary['n_ok']} weak={summary['n_weak']} elapsed={summary['elapsed_s']}s")
    require_pass(summary)


if __name__ == "__main__":
    main()
