#!/usr/bin/env python3
"""Stage 001.00: PDF pages to canonical Paddle OCR JSON and local QA.

Inputs: source PDF pages
Outputs: 001.00-paddle-ocr/pages/*.json and qa/summary.json
"""

from __future__ import annotations

import argparse
import time
from typing import Any, Iterable

import numpy as np
import pymupdf

from _common import add_stage_arguments, make_context, require_pass
from _shared.artifacts import write_json_atomic
from _shared.contracts import stamp_meta
from _shared.raster import render_page_rgb
from _shared.timestamps import iso_now


def build_ocr(*, lang: str = "en", device: str = "gpu:0") -> Any:
    """Construct the reviewed PaddleOCR 3.x configuration used by v2."""
    from paddleocr import PaddleOCR

    return PaddleOCR(
        lang=lang,
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_textline_orientation=False,
        return_word_box=True,
        device=device,
    )


def run_ocr(engine: Any, image_rgb: np.ndarray) -> Any:
    """Run PaddleOCR with the BGR convention used by the proven v1 burn."""
    image_bgr = image_rgb[:, :, ::-1].copy()
    if not hasattr(engine, "predict"):
        raise TypeError("PaddleOCR v2 requires the PaddleOCR 3.x predict API")
    try:
        return engine.predict(image_bgr, return_word_box=True)
    except TypeError:
        return engine.predict(image_bgr)


def _get(payload: Any, key: str) -> Any:
    if isinstance(payload, dict):
        return payload.get(key)
    if hasattr(payload, "get"):
        try:
            return payload.get(key)
        except Exception:  # model Result mappings vary by Paddle patch release
            return None
    try:
        return payload[key]
    except (KeyError, TypeError, IndexError):
        return None


def _first(payload: Any, keys: Iterable[str]) -> Any:
    for key in keys:
        value = _get(payload, key)
        if value is not None:
            return value
    return None


def _polygon(value: Any) -> list[list[float]]:
    array = np.asarray(value, dtype=float)
    if array.ndim == 1 and array.size == 4:
        x0, y0, x1, y1 = array.tolist()
        return [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]
    if array.ndim == 2 and array.shape[1] >= 2:
        return [[float(point[0]), float(point[1])] for point in array]
    raise ValueError(f"unrecognized Paddle box shape: {array.shape}")


def _bbox_pdf(value: Any, *, dpi: float) -> list[float]:
    if dpi <= 0:
        raise ValueError(f"dpi must be positive: {dpi}")
    scale = 72.0 / dpi
    polygon = _polygon(value)
    xs = [point[0] * scale for point in polygon]
    ys = [point[1] * scale for point in polygon]
    return [
        round(min(xs), 2),
        round(min(ys), 2),
        round(max(xs), 2),
        round(max(ys), 2),
    ]


def _payload_keys(payload: Any) -> list[str]:
    try:
        return sorted(str(key) for key in payload.keys())
    except (AttributeError, TypeError):
        return []


def parse_ocr_result(raw: Any, *, dpi: float) -> dict[str, Any]:
    """Normalize PaddleOCR 3.x results without serializing model internals."""
    payloads = raw if isinstance(raw, list) else [raw]
    tokens: list[dict[str, Any]] = []
    lines: list[dict[str, Any]] = []
    observed_keys: set[str] = set()

    for payload in payloads:
        if payload is None:
            continue
        observed_keys.update(_payload_keys(payload))
        nested = _get(payload, "res")
        if nested is not None and _first(payload, ("rec_texts", "texts")) is None:
            nested_result = parse_ocr_result(nested, dpi=dpi)
            token_offset = len(tokens)
            line_offset = len(lines)
            for token in nested_result["tokens"]:
                copied = dict(token)
                copied["line_id"] = int(copied["line_id"]) + line_offset
                tokens.append(copied)
            for line in nested_result["lines"]:
                copied = dict(line)
                copied["line_id"] = int(copied["line_id"]) + line_offset
                copied["token_ids"] = [
                    int(value) + token_offset for value in copied["token_ids"]
                ]
                lines.append(copied)
            observed_keys.update(nested_result["diagnostics"]["raw_keys"])
            continue

        texts = _first(payload, ("rec_texts", "texts"))
        scores = _first(payload, ("rec_scores", "scores"))
        polygons = _first(payload, ("dt_polys", "rec_polys", "boxes"))
        words = _get(payload, "text_word")
        word_boxes = _first(payload, ("text_word_boxes", "text_word_region"))
        if texts is None or polygons is None:
            continue

        for index, line_text in enumerate(texts):
            line_id = len(lines)
            confidence = (
                round(float(scores[index]), 4) if scores is not None else None
            )
            line_bbox = _bbox_pdf(polygons[index], dpi=dpi)
            token_ids: list[int] = []
            line_words = list(words[index]) if words is not None and index < len(words) else []
            line_boxes = list(word_boxes[index]) if word_boxes is not None and index < len(word_boxes) else []
            for word, box in zip(line_words, line_boxes):
                text = str(word).strip()
                if not text:
                    continue
                token_id = len(tokens)
                tokens.append(
                    {
                        "text": text,
                        "bbox": _bbox_pdf(box, dpi=dpi),
                        "confidence": confidence,
                        "source": "paddle",
                        "line_id": line_id,
                    }
                )
                token_ids.append(token_id)
            if not token_ids:
                token_id = len(tokens)
                tokens.append(
                    {
                        "text": str(line_text),
                        "bbox": line_bbox,
                        "confidence": confidence,
                        "source": "paddle",
                        "line_id": line_id,
                    }
                )
                token_ids.append(token_id)
            lines.append(
                {
                    "line_id": line_id,
                    "text": str(line_text),
                    "bbox": line_bbox,
                    "token_ids": token_ids,
                    "confidence": confidence,
                    "source": "paddle",
                }
            )

    confidences = [
        float(token["confidence"])
        for token in tokens
        if token.get("confidence") is not None
    ]
    return {
        "tokens": tokens,
        "lines": lines,
        "stats": {
            "n_tokens": len(tokens),
            "n_lines": len(lines),
            "mean_confidence": (
                round(sum(confidences) / len(confidences), 6)
                if confidences
                else None
            ),
        },
        "diagnostics": {
            "raw_type": type(raw).__name__,
            "raw_keys": sorted(observed_keys),
            "word_boxes_used": any(len(line["token_ids"]) > 1 for line in lines),
        },
    }


def extract_paddle(
    image_rgb: np.ndarray, *, dpi: float, engine: Any
) -> dict[str, Any]:
    return parse_ocr_result(run_ocr(engine, image_rgb), dpi=dpi)


def run_stage(context, *, engine: Any | None = None) -> dict[str, Any]:
    results = []
    started_at, started = iso_now(), time.perf_counter()
    engine = engine or build_ocr(device=context.device)
    with pymupdf.open(context.pdf) as document:
        for page_no in context.pages:
            page_started_at, page_started = iso_now(), time.perf_counter()
            try:
                if not 1 <= page_no <= document.page_count:
                    raise ValueError(f"page {page_no} outside PDF range 1..{document.page_count}")
                image, page_size = render_page_rgb(document[page_no - 1], dpi=context.dpi)
                payload = extract_paddle(image, dpi=context.dpi, engine=engine)
                payload.update({"page": page_no,
                    "page_size_pt": [round(value, 2) for value in page_size],
                    "image_size_px": [int(image.shape[1]), int(image.shape[0])]})
                stamp_meta(payload, stage="layer:paddle", producer="PaddleOCR")
                write_json_atomic(context.store.layer_path("paddle", page_no), payload)
                result = {"page": page_no, "pass": True, **payload["stats"], **payload["diagnostics"]}
            except Exception as error:
                result = {"page": page_no, "pass": False,
                          "error_type": type(error).__name__, "error": str(error)}
            result.update({"started_at": page_started_at, "completed_at": iso_now(),
                           "timestamp_source": "captured",
                           "elapsed_s": round(time.perf_counter() - page_started, 3)})
            results.append(result)
    n_fail = sum(not result["pass"] for result in results)
    summary = {"artifact_version": 1, "gate": "EXTRACT_PADDLE",
        "name": "paddle_ocr_layer", "canonical": True,
        "n_pages": len(results), "n_fail": n_fail,
        "started_at": started_at, "completed_at": iso_now(),
        "timestamp_source": "captured", "elapsed_s": round(time.perf_counter() - started, 3),
        "settings": {"dpi": context.dpi, "device": context.device, "return_word_box": True},
        "pages": results, "pass": n_fail == 0}
    write_json_atomic(context.store.stage_qa_path("paddle"), summary)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    add_stage_arguments(parser, gpu=True)
    context = make_context(parser.parse_args())
    summary = run_stage(context)
    print(f"001.00 Paddle OCR: pages={summary['n_pages']} fail={summary['n_fail']} elapsed={summary['elapsed_s']}s")
    require_pass(summary)


if __name__ == "__main__":
    main()
