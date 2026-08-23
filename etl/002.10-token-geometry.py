#!/usr/bin/env python3
"""Stage 002.10: OCR tokens to deterministic token-geometry measurements.

Inputs: 001.00 Paddle token JSON
Outputs: 002.10-token-geometry/pages/*.json and qa/summary.json

Measures bands, gaps, phrases, marker/money evidence, recurring right edges,
and skew candidates. It does not infer table schemas, rows, or cells.
"""
from __future__ import annotations

import argparse
import re
import statistics
import time
from typing import Any

from _common import add_stage_arguments, make_context, require_pass
from _shared.artifacts import read_json, write_json_atomic
from _shared.contracts import stamp_meta
from _shared.timestamps import iso_now

COMMA_MONEY = re.compile(r"^\d{1,3}(?:,\d{3})+(?:\.\d+)?$")
BARE_NUMBER = re.compile(r"^\d+(?:\.\d+)?$")
MARKER = re.compile(r"^(?:\d{1,2}|[A-Za-z])[.)]$")
PARAMETERS = {
    "baseline_height_fraction": 0.22, "baseline_tolerance_min_pt": 1.25,
    "baseline_tolerance_max_pt": 3.0, "phrase_gap_spaces": 3.0,
    "phrase_gap_min_pt": 9.0, "marker_gap_min_pt": 9.0,
    "column_max_total_offset_fraction": 0.38,
    "column_min_members": 3,
}


def _median(values: list[float], default: float = 0.0) -> float:
    return float(statistics.median(values)) if values else default


def _mad(values: list[float]) -> float:
    center = _median(values)
    return _median([abs(value - center) for value in values])


def _union(boxes: list[list[float]]) -> list[float]:
    return [round(min(b[0] for b in boxes), 2), round(min(b[1] for b in boxes), 2),
            round(max(b[2] for b in boxes), 2), round(max(b[3] for b in boxes), 2)]


def _join(items: list[dict[str, Any]]) -> str:
    result = ""
    for item in items:
        value = str(item.get("text") or "").strip()
        if not value:
            continue
        if not result or value in {".", ",", ")", ":", ";", "%"} or result.endswith("("):
            result += value
        else:
            result += " " + value
    return result.strip()


def _char_width(token: dict[str, Any]) -> float | None:
    count = len(re.sub(r"\s+", "", str(token.get("text") or "")))
    return (token["bbox"][2] - token["bbox"][0]) / count if count >= 2 else None


def _vertical_overlap(a: list[float], b: list[float]) -> float:
    overlap = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    return overlap / max(min(a[3] - a[1], b[3] - b[1]), 0.01)


def _line_fit(points: list[tuple[float, float]]) -> tuple[float, float]:
    if len(points) < 2:
        return 0.0, points[0][1] if points else 0.0
    xm, ym = statistics.fmean(x for x, _ in points), statistics.fmean(y for _, y in points)
    denominator = sum((x - xm) ** 2 for x, _ in points)
    slope = sum((x - xm) * (y - ym) for x, y in points) / denominator if denominator else 0.0
    return slope, ym - slope * xm


def _column_drift(phrases: list[dict[str, Any]]) -> float:
    """Robustly estimate shared right-edge dx/dy without assuming one column."""
    points = [((p["bbox"][1] + p["bbox"][3]) / 2, p["bbox"][2]) for p in phrases]
    slopes = []
    for index, (y, x) in enumerate(points):
        for next_y, next_x in points[index + 1:]:
            dy = next_y - y
            # Nearby vertical observations with similar x are likely the same
            # physical column even on a multi-column page.
            if 8 <= abs(dy) <= 120 and abs(next_x - x) <= 12:
                slopes.append((next_x - x) / dy)
    slope = _median(slopes)
    return slope if abs(slope) <= 0.05 else 0.0


def _observation(text: str) -> tuple[str, float]:
    compact = re.sub(r"\s+", "", text)
    if MARKER.fullmatch(compact):
        return "marker_candidate", 1.0
    if COMMA_MONEY.fullmatch(compact):
        return "money_candidate", 1.0
    if BARE_NUMBER.fullmatch(compact):
        return "money_candidate", 0.45
    if re.search(r"\d", compact) and re.search(r"[^\d,.()\-]", compact):
        return "mixed_candidate", 0.0
    return "text_candidate", 0.0


def derive_token_geometry(tokens: list[dict[str, Any]], *, page_size: list[float]) -> dict[str, Any]:
    usable = [(i, t) for i, t in enumerate(tokens) if t.get("bbox")
              and str(t.get("text") or "").strip() and not t.get("chrome")]
    heights = [t["bbox"][3] - t["bbox"][1] for _, t in usable]
    median_height = _median(heights, 8.0)
    tolerance = max(PARAMETERS["baseline_tolerance_min_pt"],
                    min(PARAMETERS["baseline_tolerance_max_pt"],
                        median_height * PARAMETERS["baseline_height_fraction"]))
    page_char_width = _median([value for _, t in usable if (value := _char_width(t)) is not None],
                              max(median_height * 0.45, 1.0))
    source_lines: dict[int, list[dict[str, Any]]] = {}
    for _, token in usable:
        if token.get("line_id") is not None:
            source_lines.setdefault(int(token["line_id"]), []).append(token)
    ordinary_gaps = []
    for line_tokens in source_lines.values():
        ordered = sorted(line_tokens, key=lambda t: t["bbox"][0])
        ordinary_gaps.extend(
            gap for left, right in zip(ordered, ordered[1:])
            if 0 < (gap := right["bbox"][0] - left["bbox"][2]) <= median_height * 2
        )
    page_space_width = _median(ordinary_gaps, max(page_char_width * 1.5, 1.0))

    # Non-single-link bottom clustering: the running median prevents row drift.
    raw_bands: list[dict[str, Any]] = []
    for token_id, token in sorted(usable, key=lambda item: (item[1]["bbox"][3], item[1]["bbox"][0], item[0])):
        bottom = float(token["bbox"][3])
        choices = [(abs(bottom - b["baseline_y"]), index) for index, b in enumerate(raw_bands)
                   if abs(bottom - b["baseline_y"]) <= tolerance]
        if choices:
            band = raw_bands[min(choices)[1]]
            band["token_ids"].append(token_id); band["bottoms"].append(bottom)
            band["baseline_y"] = _median(band["bottoms"])
        else:
            raw_bands.append({"baseline_y": bottom, "bottoms": [bottom], "token_ids": [token_id]})
    raw_bands.sort(key=lambda b: (b["baseline_y"], min(tokens[i]["bbox"][0] for i in b["token_ids"])))

    bands: list[dict[str, Any]] = []
    gaps: list[dict[str, Any]] = []
    phrases: list[dict[str, Any]] = []
    for band_id, raw in enumerate(raw_bands):
        ids = sorted(raw["token_ids"], key=lambda i: (tokens[i]["bbox"][0], i))
        boxes = [tokens[i]["bbox"] for i in ids]
        bbox = _union(boxes)
        height = _median([b[3] - b[1] for b in boxes], median_height)
        char_width = _median([value for i in ids if (value := _char_width(tokens[i])) is not None], page_char_width)
        local_gaps = [gap for left, right in zip(ids, ids[1:])
                      if 0 < (gap := tokens[right]["bbox"][0] - tokens[left]["bbox"][2]) <= height * 2]
        space_width = _median(local_gaps, page_space_width) if len(local_gaps) >= 3 else page_space_width
        representative = [bbox[0], raw["baseline_y"] - height, bbox[2], raw["baseline_y"]]
        assignments = []
        for i in ids:
            box = tokens[i]["bbox"]
            delta = abs(box[3] - raw["baseline_y"])
            bottom_score = max(0.0, 1.0 - delta / max(tolerance, 0.01))
            overlap = _vertical_overlap(box, representative)
            height_score = max(0.0, 1.0 - abs((box[3] - box[1]) - height) / max(height, 0.01))
            confidence = .55 * bottom_score + .30 * overlap + .15 * height_score
            assignments.append({"token_id": i, "bottom_delta": round(delta, 3),
                                "vertical_overlap": round(overlap, 3),
                                "height_compatibility": round(height_score, 3),
                                "confidence": round(confidence, 3)})

        split_positions: dict[int, str] = {}
        band_gaps = []
        for position in range(1, len(ids)):
            left, right = tokens[ids[position - 1]], tokens[ids[position]]
            gap_pt = float(right["bbox"][0]) - float(left["bbox"][2])
            spaces = gap_pt / max(space_width, 0.01)
            if (gap_pt >= PARAMETERS["phrase_gap_min_pt"]
                    and spaces >= PARAMETERS["phrase_gap_spaces"]):
                split_positions[position] = "gap_spaces"
            gap = {"gap_id": len(gaps), "band_id": band_id,
                   "left_token_id": ids[position - 1], "right_token_id": ids[position],
                   "bbox": [round(left["bbox"][2], 2), round(min(left["bbox"][1], right["bbox"][1]), 2),
                            round(right["bbox"][0], 2), round(max(left["bbox"][3], right["bbox"][3]), 2)],
                   "gap_pt": round(gap_pt, 3), "estimated_spaces": round(spaces, 3),
                   "split": False, "reason": None}
            gaps.append(gap); band_gaps.append(gap)
        for end in (1, 2):
            if len(ids) <= end:
                continue
            prefix = _join([tokens[i] for i in ids[:end]]).replace(" ", "")
            if not MARKER.fullmatch(prefix):
                continue
            marker_left = float(tokens[ids[0]]["bbox"][0])
            next_left = float(tokens[ids[end]]["bbox"][0])
            expected_width = len(prefix) * char_width
            compensated_gap = next_left - marker_left - expected_width
            compensated_spaces = compensated_gap / max(space_width, .01)
            marker_gap = band_gaps[end - 1]
            raw_spaces = marker_gap["estimated_spaces"]
            effective_spaces = max(raw_spaces, compensated_spaces)
            marker_gap.update({
                "raw_gap_pt": marker_gap["gap_pt"],
                "raw_gap_spaces": raw_spaces,
                "left_edge_span_pt": round(next_left - marker_left, 3),
                "expected_marker_width_pt": round(expected_width, 3),
                "compensated_gap_pt": round(compensated_gap, 3),
                "compensated_gap_spaces": round(compensated_spaces, 3),
                "marker_width_disagreement_pt": round(
                    abs(compensated_gap - marker_gap["gap_pt"]), 3
                ),
                "marker_effective_gap_spaces": round(effective_spaces, 3),
            })
            effective_gap_pt = max(marker_gap["gap_pt"], compensated_gap)
            marker_gap["marker_effective_gap_pt"] = round(effective_gap_pt, 3)
            if effective_gap_pt >= PARAMETERS["marker_gap_min_pt"]:
                split_positions[end] = (
                    "marker_compensated_gap"
                    if compensated_spaces > raw_spaces else "marker_raw_gap"
                )
                break
        for position, reason in split_positions.items():
            band_gaps[position - 1].update({"split": True, "reason": reason})

        chunks: list[list[int]] = [[]]
        for position, token_id in enumerate(ids):
            if position in split_positions:
                chunks.append([])
            chunks[-1].append(token_id)
        phrase_ids = []
        for chunk in chunks:
            text = _join([tokens[i] for i in chunk])
            observation, lexical_confidence = _observation(text)
            phrase_id = len(phrases)
            phrases.append({"phrase_id": phrase_id, "band_id": band_id, "text": text,
                            "bbox": _union([tokens[i]["bbox"] for i in chunk]), "token_ids": chunk,
                            "source_line_ids": sorted({tokens[i].get("line_id") for i in chunk
                                                       if tokens[i].get("line_id") is not None}),
                            "observation": observation,
                            "money_lexical_confidence": lexical_confidence,
                            "amount_context_confidence": 0.0})
            phrase_ids.append(phrase_id)
        points = [((tokens[i]["bbox"][0] + tokens[i]["bbox"][2]) / 2, tokens[i]["bbox"][3]) for i in ids]
        slope, intercept = _line_fit(points)
        residuals = [abs(y - (slope * x + intercept)) for x, y in points]
        bands.append({"band_id": band_id, "bbox": bbox, "baseline_y": round(raw["baseline_y"], 3),
                      "baseline_segment": [bbox[0], round(slope * bbox[0] + intercept, 3),
                                           bbox[2], round(slope * bbox[2] + intercept, 3)],
                      "fit_slope": round(slope, 7), "fit_mad": round(_mad(residuals), 3),
                      "confidence": round(_median([a["confidence"] for a in assignments]), 3),
                      "estimated_char_width": round(char_width, 3),
                      "estimated_space_width": round(space_width, 3), "token_ids": ids,
                      "phrase_ids": phrase_ids,
                      "source_line_ids": sorted({tokens[i].get("line_id") for i in ids
                                                 if tokens[i].get("line_id") is not None}),
                      "assignments": assignments})

    page_width = float(page_size[0]) if page_size else max((t["bbox"][2] for _, t in usable), default=1.0)
    money_observations = [p for p in phrases if p["observation"] == "money_candidate"
                          and len(re.sub(r"\D", "", p["text"])) >= 4]
    provisional_total_x = max((p["bbox"][2] for p in money_observations), default=page_width)
    column_search_left_x = provisional_total_x - (
        page_width * PARAMETERS["column_max_total_offset_fraction"]
    )
    money = [p for p in money_observations if p["bbox"][2] >= column_search_left_x]
    page_height = float(page_size[1]) if len(page_size) > 1 else max(
        (t["bbox"][3] for _, t in usable), default=1.0)
    reference_y = page_height / 2
    drift_slope = _column_drift(money)
    raw_columns: list[dict[str, Any]] = []
    column_tolerance = max(6.0, page_char_width * 1.5)
    for phrase in sorted(money, key=lambda p: (p["bbox"][2], p["bbox"][3])):
        right = float(phrase["bbox"][2])
        center_y = (phrase["bbox"][1] + phrase["bbox"][3]) / 2
        corrected_right = right - drift_slope * (center_y - reference_y)
        phrase["right_edge_anchor"] = {
            "raw_x": round(right, 3), "corrected_x": round(corrected_right, 3),
            "center_y": round(center_y, 3), "drift_slope_dx_dy": round(drift_slope, 7),
        }
        choices = [(abs(corrected_right - c["right_x"]), index)
                   for index, c in enumerate(raw_columns)
                   if abs(corrected_right - c["right_x"]) <= column_tolerance]
        if choices:
            column = raw_columns[min(choices)[1]]
            column["phrase_ids"].append(phrase["phrase_id"])
            column["raw_rights"].append(right)
            column["rights"].append(corrected_right)
            column["right_x"] = _median(column["rights"])
        else:
            raw_columns.append({"right_x": corrected_right, "rights": [corrected_right],
                                "raw_rights": [right], "phrase_ids": [phrase["phrase_id"]]})
    raw_columns.sort(key=lambda c: c["right_x"])

    columns, fits = [], []
    for column_id, raw in enumerate(raw_columns):
        members = [phrases[i] for i in raw["phrase_ids"]]
        recurring = len(members) >= PARAMETERS["column_min_members"]
        right_mad = _mad(raw["rights"])
        context = min(1.0, len(members) / PARAMETERS["column_min_members"]) * max(0.0, 1.0 - right_mad / column_tolerance)
        for phrase in members:
            phrase["amount_context_confidence"] = round(context, 3)
        y0, y1 = min(p["bbox"][1] for p in members), max(p["bbox"][3] for p in members)
        line_segment = [round(raw["right_x"] + drift_slope * (y0 - reference_y), 2), round(y0, 2),
                        round(raw["right_x"] + drift_slope * (y1 - reference_y), 2), round(y1, 2)]
        corrected_lefts = [p["bbox"][0] - drift_slope *
                           (((p["bbox"][1] + p["bbox"][3]) / 2) - reference_y)
                           for p in members]
        amount_left_x = min(corrected_lefts)
        left_line_segment = [round(amount_left_x + drift_slope * (y0 - reference_y), 2), round(y0, 2),
                             round(amount_left_x + drift_slope * (y1 - reference_y), 2), round(y1, 2)]
        columns.append({"column_id": column_id, "bbox": _union([p["bbox"] for p in members]),
                        "right_x": round(raw["right_x"], 3), "right_mad": round(right_mad, 3),
                        "right_x_reference_y": round(reference_y, 3),
                        "raw_right_x_median": round(_median(raw["raw_rights"]), 3),
                        "drift_slope_dx_dy": round(drift_slope, 7),
                        "line_segment": line_segment,
                        "amount_left_x": round(amount_left_x, 3),
                        "left_line_segment": left_line_segment,
                        "tolerance": round(column_tolerance, 3), "phrase_ids": raw["phrase_ids"],
                        "n_phrases": len(members), "recurring": recurring,
                        "support": "recurring_amount_anchors" if recurring else "singleton_amount_anchor",
                        "review": not recurring})
        slopes, pair_ids, segments = [], [], []
        for amount in members:
            peers = [phrases[i] for i in bands[amount["band_id"]]["phrase_ids"]
                     if phrases[i]["bbox"][2] < amount["bbox"][0]
                     and phrases[i]["observation"] not in {"marker_candidate", "money_candidate"}]
            if not peers:
                continue
            left = min(peers, key=lambda p: p["bbox"][0])
            lx, ly = (left["bbox"][0] + left["bbox"][2]) / 2, left["bbox"][3]
            ax, ay = (amount["bbox"][0] + amount["bbox"][2]) / 2, amount["bbox"][3]
            if ax - lx >= 40:
                slopes.append((ay - ly) / (ax - lx)); pair_ids.append([left["phrase_id"], amount["phrase_id"]])
                segments.append([round(lx, 2), round(ly, 2), round(ax, 2), round(ay, 2)])
        fits.append({"fit_id": len(fits), "column_id": column_id, "slope": round(_median(slopes), 7),
                     "slope_mad": round(_mad(slopes), 7), "n_pairs": len(slopes),
                     "pair_phrase_ids": pair_ids, "segments": segments,
                     "review": len(slopes) < PARAMETERS["column_min_members"]})

    label_phrases = [p for p in phrases
                     if p["observation"] not in {"marker_candidate", "money_candidate"}]
    raw_indents: list[dict[str, Any]] = []
    indent_tolerance = max(3.0, page_char_width)
    for phrase in sorted(label_phrases, key=lambda p: (p["bbox"][0], p["bbox"][1])):
        center_y = (phrase["bbox"][1] + phrase["bbox"][3]) / 2
        corrected_left = phrase["bbox"][0] - drift_slope * (center_y - reference_y)
        choices = [(abs(corrected_left - group["left_x"]), index)
                   for index, group in enumerate(raw_indents)
                   if abs(corrected_left - group["left_x"]) <= indent_tolerance]
        if choices:
            group = raw_indents[min(choices)[1]]
            group["phrase_ids"].append(phrase["phrase_id"])
            group["lefts"].append(corrected_left)
            group["left_x"] = _median(group["lefts"])
        else:
            raw_indents.append({"left_x": corrected_left, "lefts": [corrected_left],
                                "phrase_ids": [phrase["phrase_id"]]})
    raw_indents.sort(key=lambda group: group["left_x"])
    label_indents = []
    for indent_id, raw in enumerate(raw_indents):
        members = [phrases[i] for i in raw["phrase_ids"]]
        y0, y1 = min(p["bbox"][1] for p in members), max(p["bbox"][3] for p in members)
        segment = [round(raw["left_x"] + drift_slope * (y0 - reference_y), 2), round(y0, 2),
                   round(raw["left_x"] + drift_slope * (y1 - reference_y), 2), round(y1, 2)]
        label_indents.append({"indent_id": indent_id, "left_x": round(raw["left_x"], 3),
                              "left_mad": round(_mad(raw["lefts"]), 3),
                              "drift_slope_dx_dy": round(drift_slope, 7), "line_segment": segment,
                              "phrase_ids": raw["phrase_ids"], "n_phrases": len(members),
                              "support": "recurring_label_indent" if len(members) >= 2 else "singleton_label_indent",
                              "review": len(members) < 2})

    separators = []
    for amount in money:
        peers = [phrases[i] for i in bands[amount["band_id"]]["phrase_ids"]
                 if phrases[i]["bbox"][2] < amount["bbox"][0]
                 and phrases[i]["observation"] not in {"marker_candidate", "money_candidate"}]
        if not peers:
            continue
        label = max(peers, key=lambda p: p["bbox"][2])
        left, right = label["bbox"][2], amount["bbox"][0]
        if right <= left:
            continue
        y0 = min(label["bbox"][1], amount["bbox"][1])
        y1 = max(label["bbox"][3], amount["bbox"][3])
        separators.append({"separator_id": len(separators), "band_id": amount["band_id"],
                           "label_phrase_id": label["phrase_id"], "amount_phrase_id": amount["phrase_id"],
                           "x": round((left + right) / 2, 3), "gap_pt": round(right - left, 3),
                           "line_segment": [round((left + right) / 2, 2), round(y0, 2),
                                            round((left + right) / 2, 2), round(y1, 2)],
                           "review": True})

    assigned = {token_id for band in bands for token_id in band["token_ids"]}
    confidences = [a["confidence"] for band in bands for a in band["assignments"]]
    return {"algorithm": {"name": "deterministic_token_geometry", "version": 1, "parameters": PARAMETERS},
            "baseline_bands": bands, "gaps": gaps, "phrases": phrases,
            "column_candidates": columns, "label_indent_anchors": label_indents,
            "separator_candidates": separators, "fit_candidates": fits,
            "unassigned_token_ids": [i for i in range(len(tokens)) if i not in assigned],
            "diagnostics": {"median_token_height": round(median_height, 3),
                            "baseline_tolerance": round(tolerance, 3),
                            "estimated_page_char_width": round(page_char_width, 3),
                            "estimated_page_space_width": round(page_space_width, 3),
                            "n_input_tokens": len(tokens), "n_usable_tokens": len(usable),
                            "n_bands": len(bands), "n_gaps": len(gaps),
                            "n_split_gaps": sum(g["split"] for g in gaps), "n_phrases": len(phrases),
                            "n_marker_candidates": sum(p["observation"] == "marker_candidate" for p in phrases),
                            "n_money_candidates": sum(p["observation"] == "money_candidate" for p in phrases),
                            "n_amount_anchor_observations": len(money),
                            "provisional_total_right_x": round(provisional_total_x, 3),
                            "column_search_left_x": round(column_search_left_x, 3),
                            "n_recurring_columns": sum(c["recurring"] for c in columns),
                            "n_label_indent_anchors": len(label_indents),
                            "n_separator_candidates": len(separators),
                            "column_drift_slope_dx_dy": round(drift_slope, 7),
                            "column_drift_across_page_pt": round(drift_slope * page_height, 3),
                            "mean_assignment_confidence": round(statistics.fmean(confidences), 4) if confidences else None}}


def run_stage(context) -> dict[str, Any]:
    results = []; started_at, started = iso_now(), time.perf_counter()
    for page_no in context.pages:
        page_started_at, page_started = iso_now(), time.perf_counter()
        try:
            paddle = read_json(context.store.layer_path("paddle", page_no))
            payload = derive_token_geometry(paddle.get("tokens") or [], page_size=list(paddle.get("page_size_pt") or []))
            payload.update({"page": page_no, "page_size_pt": paddle.get("page_size_pt"), "image_size_px": paddle.get("image_size_px")})
            stamp_meta(payload, stage="layer:token_geometry", producer="deterministic_token_geometry_v1")
            write_json_atomic(context.store.layer_path("token_geometry", page_no), payload)
            result = {"page": page_no, "pass": True, **payload["diagnostics"]}
        except Exception as error:
            result = {"page": page_no, "pass": False, "error_type": type(error).__name__, "error": str(error)}
        result.update({"started_at": page_started_at, "completed_at": iso_now(), "timestamp_source": "captured", "elapsed_s": round(time.perf_counter() - page_started, 3)})
        results.append(result)
    n_fail = sum(not result["pass"] for result in results)
    summary = {"artifact_version": 1, "gate": "TOKEN_GEOMETRY", "name": "deterministic_token_geometry_measurements", "scope": "measurement_only_v1", "n_pages": len(results), "n_fail": n_fail, "started_at": started_at, "completed_at": iso_now(), "timestamp_source": "captured", "elapsed_s": round(time.perf_counter() - started, 3), "pages": results, "pass": n_fail == 0}
    write_json_atomic(context.store.stage_qa_path("token_geometry"), summary)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__); add_stage_arguments(parser)
    summary = run_stage(make_context(parser.parse_args()))
    print(f"002.10 Token geometry: pages={summary['n_pages']} fail={summary['n_fail']} elapsed={summary['elapsed_s']}s")
    require_pass(summary)


if __name__ == "__main__":
    main()
