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
PROGRAM_CODE = re.compile(r"^\d{12,}$")
CURRENCY_MONEY = re.compile(r"^P(?:HP)?\d[\d,]*(?:\.\d+)?$", re.I)
CURRENCY_START = re.compile(r"^P(?:HP)?(?:\d+)?$", re.I)
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


def _cluster_token_bottoms(usable: list[tuple[int, dict[str, Any]]],
                           tokens: list[dict[str, Any]], tolerance: float, *,
                           slope: float = 0.0, reference_x: float = 0.0) -> list[dict[str, Any]]:
    raw_bands: list[dict[str, Any]] = []
    observations = []
    for token_id, token in usable:
        box = token["bbox"]
        raw_bottom = float(box[3])
        center_x = (float(box[0]) + float(box[2])) / 2
        corrected_bottom = raw_bottom - slope * (center_x - reference_x)
        observations.append((corrected_bottom, float(box[0]), token_id, raw_bottom))
    for corrected_bottom, _, token_id, raw_bottom in sorted(observations):
        choices = [(abs(corrected_bottom - band["baseline_y"]), index)
                   for index, band in enumerate(raw_bands)
                   if abs(corrected_bottom - band["baseline_y"]) <= tolerance]
        if choices:
            band = raw_bands[min(choices)[1]]
            band["token_ids"].append(token_id)
            band["bottoms"].append(corrected_bottom)
            band["raw_bottoms"].append(raw_bottom)
            band["baseline_y"] = _median(band["bottoms"])
        else:
            raw_bands.append({"baseline_y": corrected_bottom,
                              "bottoms": [corrected_bottom],
                              "raw_bottoms": [raw_bottom],
                              "token_ids": [token_id], "slope": slope})
    raw_bands.sort(key=lambda band: (
        band["baseline_y"], min(tokens[index]["bbox"][0] for index in band["token_ids"])))
    return raw_bands


def _page_baseline_slope(raw_bands: list[dict[str, Any]], tokens: list[dict[str, Any]],
                         page_width: float, tolerance: float, *,
                         min_span: float | None = None) -> dict[str, Any]:
    candidates = []
    for band in raw_bands:
        ids = band["token_ids"]
        if len(ids) < 3:
            continue
        points = [((float(tokens[index]["bbox"][0]) + float(tokens[index]["bbox"][2])) / 2,
                   float(tokens[index]["bbox"][3])) for index in ids]
        span = max(x for x, _ in points) - min(x for x, _ in points)
        bottom_range = max(y for _, y in points) - min(y for _, y in points)
        if span < (min_span if min_span is not None else max(150.0, page_width * 0.3)) or bottom_range < 0.25:
            continue
        slope, intercept = _line_fit(points)
        residual_mad = _mad([abs(y - (slope * x + intercept)) for x, y in points])
        if abs(slope) <= 0.02 and residual_mad <= tolerance * 0.25:
            candidates.append({"slope": slope, "residual_mad": residual_mad,
                               "span": span, "n_tokens": len(ids)})
    initial = _median([candidate["slope"] for candidate in candidates])
    slope_mad = _mad([candidate["slope"] for candidate in candidates])
    radius = max(0.0015, slope_mad * 3)
    consensus = [candidate for candidate in candidates
                 if abs(candidate["slope"] - initial) <= radius]
    slope = _median([candidate["slope"] for candidate in consensus])
    consensus_mad = _mad([candidate["slope"] for candidate in consensus])
    accepted = len(consensus) >= 3 and abs(slope) <= 0.02 and consensus_mad <= 0.0025
    support_score = min(1.0, len(consensus) / 6)
    agreement_score = max(0.0, 1.0 - consensus_mad / 0.0025)
    confidence = support_score * agreement_score if accepted else 0.0
    return {"slope": slope if accepted else 0.0, "accepted": accepted,
            "confidence": confidence, "n_candidates": len(candidates),
            "n_support": len(consensus), "slope_mad": consensus_mad,
            "median_span": _median([candidate["span"] for candidate in consensus])}


def _estimate_page_slope(usable, tokens, tolerance: float, page_width: float,
                         reference_x: float) -> tuple[dict[str, Any], dict[str, Any]]:
    """Bootstrap the page slope by iterating cluster -> estimate -> re-cluster.

    A skewed page fragments long rows on the first (slope-zero) pass, so the
    strict full-span filter that a clean page supports can find too few
    candidates. Estimating from short fragments first, re-clustering with that
    slope, then re-estimating at full span breaks the circular dependency
    without weakening the final acceptance test.
    """
    strict_span = max(150.0, page_width * 0.3)
    provisional = _cluster_token_bottoms(usable, tokens, tolerance)
    strict = _page_baseline_slope(provisional, tokens, page_width, tolerance)
    if strict["accepted"]:
        return strict, provisional
    relaxed = _page_baseline_slope(provisional, tokens, page_width, tolerance,
                                   min_span=60.0)
    if relaxed["accepted"]:
        recluster = _cluster_token_bottoms(
            usable, tokens, tolerance, slope=float(relaxed["slope"]),
            reference_x=reference_x)
        refined = _page_baseline_slope(recluster, tokens, page_width, tolerance)
        if refined["accepted"]:
            return refined, recluster
        return relaxed, recluster
    return strict, provisional


def _reconcile_token_bands(raw_bands: list[dict[str, Any]], tokens: list[dict[str, Any]],
                           tolerance: float, *, slope: float,
                           reference_x: float) -> tuple[list[dict[str, Any]], int]:
    bands = list(raw_bands)
    n_merges = 0
    changed = True
    while changed:
        changed = False
        for index in range(len(bands) - 1):
            first, second = bands[index], bands[index + 1]
            first_boxes = [tokens[token_id]["bbox"] for token_id in first["token_ids"]]
            second_boxes = [tokens[token_id]["bbox"] for token_id in second["token_ids"]]
            if any(min(float(a[2]), float(b[2])) - max(float(a[0]), float(b[0])) > 0.5
                   for a in first_boxes for b in second_boxes):
                continue

            # Treat each provisional band as one observation. A token-level
            # regression gives a five-fragment amount five times the influence
            # of a two-token label, even though they are two sides of one
            # printed baseline.
            def centroid(boxes: list[list[float]]) -> tuple[float, float]:
                return (_median([(float(box[0]) + float(box[2])) / 2 for box in boxes]),
                        _median([float(box[3]) for box in boxes]))

            first_x, first_y = centroid(first_boxes)
            second_x, second_y = centroid(second_boxes)
            span = abs(second_x - first_x)
            if span < 150.0:
                continue
            fitted_slope = ((second_y - first_y) / (second_x - first_x)
                            if second_x != first_x else 0.0)
            # Normal text rows are farther apart than a plausible page/text
            # baseline tilt. This cap prevents adjacent rows on opposite sides
            # of the page from being reconciled.
            if abs(fitted_slope) > 0.018:
                continue
            # The provisional bands have already passed the baseline
            # tolerance. Permit modest within-band OCR bottom variation here,
            # especially when two amount columns place otherwise aligned
            # digits about one point apart.
            if (_mad([float(box[3]) for box in first_boxes]) > tolerance * 0.5
                    or _mad([float(box[3]) for box in second_boxes]) > tolerance * 0.5):
                continue
            ids = first["token_ids"] + second["token_ids"]
            points = [((float(tokens[token_id]["bbox"][0]) +
                        float(tokens[token_id]["bbox"][2])) / 2,
                       float(tokens[token_id]["bbox"][3])) for token_id in ids]
            corrected = [y - fitted_slope * (x - reference_x) for x, y in points]
            merged = {"baseline_y": _median(corrected), "bottoms": corrected,
                      "raw_bottoms": [y for _, y in points], "token_ids": ids,
                      "slope": fitted_slope}
            bands[index:index + 2] = [merged]
            bands.sort(key=lambda band: (
                band["baseline_y"],
                min(tokens[token_id]["bbox"][0] for token_id in band["token_ids"])))
            n_merges += 1
            changed = True
            break
    return bands, n_merges


def _observation(text: str) -> tuple[str, float]:
    compact = re.sub(r"\s+", "", text)
    if MARKER.fullmatch(compact):
        return "marker_candidate", 1.0
    if PROGRAM_CODE.fullmatch(compact):
        return "code_candidate", 1.0
    if CURRENCY_MONEY.fullmatch(compact):
        return "money_candidate", 1.0
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
    # Express whitespace in character-width units. Deriving a "space width"
    # from the gaps themselves is circular and makes wide gaps look like one
    # space. A 3-space threshold therefore means roughly three characters wide.
    page_space_unit_width = page_char_width

    page_width = float(page_size[0]) if page_size else max(
        (token["bbox"][2] for _, token in usable), default=1.0)
    baseline_reference_x = page_width / 2
    page_baseline, provisional_bands = _estimate_page_slope(
        usable, tokens, tolerance, page_width, baseline_reference_x)
    raw_bands = _cluster_token_bottoms(
        usable, tokens, tolerance, slope=float(page_baseline["slope"]),
        reference_x=baseline_reference_x)
    raw_bands, n_reconciled_bands = _reconcile_token_bands(
        raw_bands, tokens, tolerance, slope=float(page_baseline["slope"]),
        reference_x=baseline_reference_x)

    bands: list[dict[str, Any]] = []
    gaps: list[dict[str, Any]] = []
    phrases: list[dict[str, Any]] = []
    for band_id, raw in enumerate(raw_bands):
        ids = sorted(raw["token_ids"], key=lambda i: (tokens[i]["bbox"][0], i))
        boxes = [tokens[i]["bbox"] for i in ids]
        bbox = _union(boxes)
        height = _median([b[3] - b[1] for b in boxes], median_height)
        char_width = _median([value for i in ids if (value := _char_width(tokens[i])) is not None], page_char_width)
        space_unit_width = char_width
        representative = [bbox[0], raw["baseline_y"] - height, bbox[2], raw["baseline_y"]]
        assignments = []
        for i in ids:
            box = tokens[i]["bbox"]
            center_x = (float(box[0]) + float(box[2])) / 2
            band_slope = float(raw.get("slope", page_baseline["slope"]))
            corrected_bottom = float(box[3]) - band_slope * (
                center_x - baseline_reference_x)
            delta = abs(corrected_bottom - raw["baseline_y"])
            bottom_score = max(0.0, 1.0 - delta / max(tolerance, 0.01))
            overlap = _vertical_overlap(box, representative)
            height_score = max(0.0, 1.0 - abs((box[3] - box[1]) - height) / max(height, 0.01))
            confidence = .55 * bottom_score + .30 * overlap + .15 * height_score
            assignments.append({"token_id": i, "bottom_delta": round(delta, 3),
                                "raw_bottom": round(float(box[3]), 3),
                                "corrected_bottom": round(corrected_bottom, 3),
                                "vertical_overlap": round(overlap, 3),
                                "height_compatibility": round(height_score, 3),
                                "confidence": round(confidence, 3)})

        split_positions: dict[int, str] = {}
        band_gaps = []
        for position in range(1, len(ids)):
            left, right = tokens[ids[position - 1]], tokens[ids[position]]
            gap_pt = float(right["bbox"][0]) - float(left["bbox"][2])
            spaces = gap_pt / max(space_unit_width, 0.01)
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

        # A leftmost long numeric token is a program-code field, not label
        # prose. Its structural boundary does not depend on the generic phrase
        # gap because compact print can legitimately leave fewer than three
        # character widths before the label.
        first_text = re.sub(r"\s+", "", str(tokens[ids[0]].get("text") or ""))
        if len(ids) > 1 and PROGRAM_CODE.fullmatch(first_text):
            split_positions[1] = "program_code_boundary"

        # A printed currency prefix is structural evidence even when the OCR
        # boxes leave less than the generic 9 pt phrase gap. Split before each
        # prefix only when the tokens through the next prefix form a complete
        # currency amount; this avoids treating an ordinary letter P as money.
        currency_starts = [position for position, token_id in enumerate(ids)
                           if CURRENCY_START.fullmatch(
                               re.sub(r"\s+", "", str(tokens[token_id].get("text") or ""))
                           )]
        for start_index, position in enumerate(currency_starts):
            end = currency_starts[start_index + 1] if start_index + 1 < len(currency_starts) else len(ids)
            compact_currency = re.sub(
                r"\s+", "", _join([tokens[token_id] for token_id in ids[position:end]])
            )
            if CURRENCY_MONEY.fullmatch(compact_currency) and position > 0:
                split_positions[position] = "currency_prefix_boundary"
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
            compensated_spaces = compensated_gap / max(space_unit_width, .01)
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
        bands.append({"band_id": band_id, "bbox": bbox,
                      "baseline_y": round(raw["baseline_y"], 3),
                      "raw_baseline_y": round(_median(raw["raw_bottoms"]), 3),
                      "baseline_reference_x": round(baseline_reference_x, 3),
                      "baseline_correction_slope": round(
                          float(raw.get("slope", page_baseline["slope"])), 7),
                      "baseline_segment": [bbox[0], round(slope * bbox[0] + intercept, 3),
                                           bbox[2], round(slope * bbox[2] + intercept, 3)],
                      "fit_slope": round(slope, 7), "fit_mad": round(_mad(residuals), 3),
                      "confidence": round(_median([a["confidence"] for a in assignments]), 3),
                      "estimated_char_width": round(char_width, 3),
                      "estimated_space_unit_width": round(space_unit_width, 3),
                      "space_unit": "character_width", "token_ids": ids,
                      "phrase_ids": phrase_ids,
                      "source_line_ids": sorted({tokens[i].get("line_id") for i in ids
                                                 if tokens[i].get("line_id") is not None}),
                      "assignments": assignments})

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
                     and phrases[i]["observation"] not in {
                         "marker_candidate", "money_candidate", "code_candidate"
                     }]
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

    recurring_columns = [column for column in columns if column["recurring"]]
    reference_columns = recurring_columns or columns
    rightmost_reference = max(reference_columns, key=lambda column: column["right_x"], default=None)
    reference_right_x = None if rightmost_reference is None else float(rightmost_reference["right_x"])
    reference_support = ("rightmost_recurring_amount_anchor" if recurring_columns
                         else "rightmost_singleton_amount_anchor" if rightmost_reference else None)
    for phrase in phrases:
        observation = phrase["observation"]
        if observation in {"marker_candidate", "code_candidate"}:
            continue
        edge = "right" if observation == "money_candidate" else "left"
        edge_index = 2 if edge == "right" else 0
        center_y = (phrase["bbox"][1] + phrase["bbox"][3]) / 2
        raw_x = float(phrase["bbox"][edge_index])
        corrected_x = raw_x - drift_slope * (center_y - reference_y)
        phrase["relative_anchor"] = {
            "alignment_edge": edge,
            "raw_x": round(raw_x, 3),
            "corrected_x": round(corrected_x, 3),
            "reference_right_x": reference_right_x,
            "distance_pt": (None if reference_right_x is None
                            else round(reference_right_x - corrected_x, 3)),
            "reference_support": reference_support,
            "drift_slope_dx_dy": round(drift_slope, 7),
        }

    money_phrase_ids = {int(phrase["phrase_id"]) for phrase in money}
    for phrase in phrases:
        if phrase["observation"] in {"text_candidate", "mixed_candidate"}:
            phrase["text_candidate_type"] = "wrapped_text_candidate"
            phrase["aligned_amount_phrase_ids"] = []
    for band in bands:
        band_phrases = [phrases[int(phrase_id)] for phrase_id in band.get("phrase_ids") or []]
        aligned_amounts = [phrase for phrase in band_phrases
                           if int(phrase["phrase_id"]) in money_phrase_ids]
        if not aligned_amounts:
            continue
        first_amount_left = min(float(phrase["bbox"][0]) for phrase in aligned_amounts)
        label_candidates = [phrase for phrase in band_phrases
                            if phrase["observation"] in {"text_candidate", "mixed_candidate"}
                            and float(phrase["bbox"][2]) < first_amount_left]
        if not label_candidates:
            continue
        main = min(label_candidates, key=lambda phrase: float(phrase["bbox"][0]))
        main["text_candidate_type"] = "main_text_candidate"
        main["aligned_amount_phrase_ids"] = sorted(
            int(phrase["phrase_id"]) for phrase in aligned_amounts)

    label_phrases = [p for p in phrases if p["observation"] not in {
        "marker_candidate", "money_candidate", "code_candidate"
    }]
    raw_indents: list[dict[str, Any]] = []
    indent_tolerance = max(3.0, page_char_width)
    for phrase in sorted(label_phrases, key=lambda p: (p["bbox"][0], p["bbox"][1])):
        corrected_left = phrase["relative_anchor"]["corrected_x"]
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
                 and phrases[i]["observation"] not in {
                     "marker_candidate", "money_candidate", "code_candidate"
                 }]
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
                            "n_provisional_bands": len(provisional_bands),
                            "n_reconciled_band_merges": n_reconciled_bands,
                            "page_baseline_slope_dy_dx": round(float(page_baseline["slope"]), 7),
                            "page_baseline_slope_accepted": bool(page_baseline["accepted"]),
                            "page_baseline_slope_confidence": round(float(page_baseline["confidence"]), 3),
                            "page_baseline_slope_candidates": int(page_baseline["n_candidates"]),
                            "page_baseline_slope_support": int(page_baseline["n_support"]),
                            "page_baseline_slope_mad": round(float(page_baseline["slope_mad"]), 7),
                            "page_baseline_slope_median_span": round(float(page_baseline["median_span"]), 3),
                            "estimated_page_char_width": round(page_char_width, 3),
                            "estimated_page_space_unit_width": round(page_space_unit_width, 3),
                            "space_unit": "character_width",
                            "n_input_tokens": len(tokens), "n_usable_tokens": len(usable),
                            "n_bands": len(bands), "n_gaps": len(gaps),
                            "n_split_gaps": sum(g["split"] for g in gaps), "n_phrases": len(phrases),
                            "n_marker_candidates": sum(p["observation"] == "marker_candidate" for p in phrases),
                            "n_money_candidates": sum(p["observation"] == "money_candidate" for p in phrases),
                            "n_main_text_candidates": sum(
                                p.get("text_candidate_type") == "main_text_candidate" for p in phrases),
                            "n_wrapped_text_candidates": sum(
                                p.get("text_candidate_type") == "wrapped_text_candidate" for p in phrases),
                            "n_amount_anchor_observations": len(money),
                            "provisional_total_right_x": round(provisional_total_x, 3),
                            "column_search_left_x": round(column_search_left_x, 3),
                            "n_recurring_columns": sum(c["recurring"] for c in columns),
                            "n_label_indent_anchors": len(label_indents),
                            "n_separator_candidates": len(separators),
                            "relative_anchor_reference_right_x": reference_right_x,
                            "relative_anchor_reference_support": reference_support,
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
