#!/usr/bin/env python3
"""Stage 002.20: token geometry to deterministic column and row sections.

Inputs: 002.10-token-geometry/pages/*.json and reviewed table seeds
Outputs: 002.20-table-structure/pages/*.json and qa/summary.json

This stage creates geometric sections using explicitly reviewed table-layout
spans. It applies table-specific row ownership but does not infer hierarchy.
"""
from __future__ import annotations

import argparse
import statistics
import time
from pathlib import Path
from typing import Any

from _common import add_stage_arguments, make_context, require_pass, resolve_project_path
from _shared.artifacts import read_json, write_json_atomic
from _shared.contracts import stamp_meta
from _shared.timestamps import iso_now


DEFAULT_SEEDS = Path("fixtures/by_ou_table_seeds.json")
DEFAULT_LAYOUTS = Path("fixtures/table_layout_spans.json")
TOP_GUTTER_Y_PT = 45.0


def _median(values: list[float], default: float = 0.0) -> float:
    return float(statistics.median(values)) if values else default


def _line_y(segment: list[float], x: float) -> float:
    x0, y0, x1, y1 = map(float, segment)
    if abs(x1 - x0) < 1e-9:
        return (y0 + y1) / 2
    return y0 + (y1 - y0) * (x - x0) / (x1 - x0)


def _line_x(segment: list[float], y: float) -> float:
    x0, y0, x1, y1 = map(float, segment)
    if abs(y1 - y0) < 1.0:
        return (x0 + x1) / 2
    return x0 + (x1 - x0) * (y - y0) / (y1 - y0)


def _polygon_bbox(polygon: list[list[float]]) -> list[float]:
    xs = [point[0] for point in polygon]
    ys = [point[1] for point in polygon]
    return [round(min(xs), 3), round(min(ys), 3),
            round(max(xs), 3), round(max(ys), 3)]


def _phrase_center(phrase: dict[str, Any]) -> tuple[float, float]:
    x0, y0, x1, y1 = map(float, phrase["bbox"])
    return (x0 + x1) / 2, (y0 + y1) / 2


def _source_ids(phrases: list[dict[str, Any]]) -> tuple[list[int], list[int]]:
    phrase_ids = sorted(int(phrase["phrase_id"]) for phrase in phrases)
    token_ids = sorted({int(token_id) for phrase in phrases
                        for token_id in phrase.get("token_ids") or []})
    return phrase_ids, token_ids


def _intersection(first: list[float], second: list[float]) -> list[float]:
    x1, y1, x2, y2 = map(float, first)
    x3, y3, x4, y4 = map(float, second)
    denominator = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    if abs(denominator) < 1e-9:
        raise ValueError("cell boundary lines are parallel")
    cross1, cross2 = x1 * y2 - y1 * x2, x3 * y4 - y3 * x4
    x = (cross1 * (x3 - x4) - (x1 - x2) * cross2) / denominator
    y = (cross1 * (y3 - y4) - (y1 - y2) * cross2) / denominator
    return [round(x, 3), round(y, 3)]


def _reviewed_page_seed(seeds: dict[str, Any] | None, page: int) -> tuple[int | None, str, dict[int, str], list[dict[str, Any]]]:
    for table in (seeds or {}).get("tables") or []:
        seed = table.get("hierarchy_seed") or {}
        expectation = next((item for item in table.get("page_expectations") or []
                            if int(item.get("page", -1)) == page), None)
        header_specs = []
        page_header_ids = (expectation or {}).get("page_header_band_ids")
        if page_header_ids:
            header_specs.append({"role": "page_header", "band_ids": page_header_ids})
        if int((table.get("start") or {}).get("page", -1)) == page:
            start = table["start"]
            if not page_header_ids and start.get("page_header_band_ids"):
                header_specs.append({"role": "page_header", "band_ids": start["page_header_band_ids"]})
            header_specs.extend([
                {"role": "table_title", "band_ids": start.get("table_title_band_ids") or []},
                {"role": "column_headers", "band_ids": start.get("column_header_band_ids") or []},
            ])
        if int(seed.get("page", -1)) == page:
            roles = {int(item["column_candidate_id"]): str(item["role"])
                     for item in (table.get("column_seed") or {}).get("roles") or []
                     if int((table.get("column_seed") or {}).get("page", -1)) == page}
            return (int(seed["band_id"]),
                    f"reviewed:{table['table_id']}:hierarchy_seed", roles,
                    [spec for spec in header_specs if spec["band_ids"]])
        if expectation:
            return None, "page_top", {}, [spec for spec in header_specs if spec["band_ids"]]
    return None, "page_top", {}, []


def _page_layout(layouts: dict[str, Any] | None, page: int) -> dict[str, Any]:
    for span in (layouts or {}).get("spans") or []:
        if int(span["start_page"]) <= page <= int(span["end_page"]):
            return {"table_type": str(span["table_type"]),
                    "wrap_direction": str(span["wrap_direction"]),
                    "source": str(span.get("source") or "reviewed_layout_span")}
    return {"table_type": "unclassified", "wrap_direction": "review",
            "source": "no_reviewed_layout_span"}


def _reviewed_band_range(seeds: dict[str, Any] | None, page: int) -> tuple[int | None, int | None]:
    for table in (seeds or {}).get("tables") or []:
        start, end = table.get("start") or {}, table.get("end") or {}
        if int(start.get("page", -1)) <= page <= int(end.get("page", -1)):
            first = int(start["body_first_band_id"]) if page == int(start["page"]) else None
            last = int(end["terminal_band_id"]) if page == int(end["page"]) else None
            return first, last
    return None, None


def _header_sections(geometry: dict[str, Any], phrases: list[dict[str, Any]],
                     specs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    width = float((geometry.get("page_size_pt") or [720.0, 864.0])[0])
    bands = {int(band["band_id"]): band for band in geometry.get("baseline_bands") or []}
    phrase_by_id = {int(phrase["phrase_id"]): phrase for phrase in phrases}
    sections = []
    for spec in specs:
        members_bands = [bands[int(band_id)] for band_id in spec["band_ids"]
                         if int(band_id) in bands]
        if not members_bands:
            continue
        y0 = min(float(band["bbox"][1]) for band in members_bands)
        y1 = max(float(band["bbox"][3]) for band in members_bands)
        phrase_ids = [int(phrase_id) for band in members_bands
                      for phrase_id in band.get("phrase_ids") or []]
        members = [phrase_by_id[phrase_id] for phrase_id in phrase_ids if phrase_id in phrase_by_id]
        members.sort(key=lambda phrase: (int(phrase.get("band_id", -1)), float(phrase["bbox"][0])))
        ordered_phrase_ids, token_ids = _source_ids(members)
        lines = []
        for band in sorted(members_bands, key=lambda item: float(item["baseline_y"])):
            line_phrases = [phrase_by_id[int(phrase_id)] for phrase_id in band.get("phrase_ids") or []
                            if int(phrase_id) in phrase_by_id]
            line_phrases.sort(key=lambda phrase: float(phrase["bbox"][0]))
            lines.append({"band_id": int(band["band_id"]),
                          "phrase_ids": [int(phrase["phrase_id"]) for phrase in line_phrases],
                          "text": " ".join(str(phrase.get("text") or "") for phrase in line_phrases).strip()})
        polygon = [[0.0, y0], [width, y0], [width, y1], [0.0, y1]]
        sections.append({
            "header_section_id": len(sections), "role": spec["role"],
            "band_ids": [int(band["band_id"]) for band in members_bands],
            "polygon": polygon, "bbox": _polygon_bbox(polygon),
            "phrase_ids": ordered_phrase_ids, "source_token_ids": token_ids,
            "lines": lines, "text": "\n".join(line["text"] for line in lines if line["text"]),
            "source": "reviewed_seed",
        })
    return sections


def _amount_column_candidates(geometry: dict[str, Any]) -> list[dict[str, Any]]:
    """Keep every amount anchor with a left edge, including sparse/non-recurring.

    Recurrence is geometry support evidence, not a license to collapse the
    lattice. Dropping sparse CO between MOOE and Total merges distinct money
    phrases into one cell.
    """
    return [column for column in geometry.get("column_candidates") or []
            if column.get("left_line_segment")]


def _column_sections(geometry: dict[str, Any], phrases: list[dict[str, Any]],
                     column_roles: dict[int, str], *,
                     first_band_id: int | None = None,
                     last_band_id: int | None = None) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    width, height = map(float, geometry.get("page_size_pt") or [720.0, 864.0])
    columns = _amount_column_candidates(geometry)
    if not columns:
        return [], [{"code": "no_recurring_amount_column", "severity": "review"}]

    columns.sort(key=lambda column: _line_x(column["left_line_segment"], height / 2))
    edges = []
    for column in columns:
        segment = list(map(float, column["left_line_segment"]))
        edges.append({"column": column, "segment": segment,
                      "x_top": min(width, max(0.0, _line_x(segment, 0.0))),
                      "x_bottom": min(width, max(0.0, _line_x(segment, height)))})
    main_labels = [phrase for phrase in phrases
                   if phrase.get("text_candidate_type") == "main_text_candidate"
                   and (first_band_id is None or int(phrase["band_id"]) >= first_band_id)
                   and (last_band_id is None or int(phrase["band_id"]) <= last_band_id)
                   and (phrase.get("relative_anchor") or {}).get("corrected_x") is not None]
    if main_labels:
        label_left_x = min(float(phrase["relative_anchor"]["corrected_x"])
                           for phrase in main_labels)
        reference_y = float(columns[-1].get("right_x_reference_y", height / 2))
        drift_slope = float(columns[-1].get("drift_slope_dx_dy", 0.0))
        label_left_top = label_left_x + drift_slope * (0.0 - reference_y)
        label_left_bottom = label_left_x + drift_slope * (height - reference_y)
        label_left_source = "main_text_anchor_distance_envelope"
    else:
        label_left_top = label_left_bottom = 0.0
        label_left_source = "page_left_fallback"
    specs = [{"role": "Labels", "candidate": None,
              "left_top": label_left_top, "left_bottom": label_left_bottom,
              "right_top": edges[0]["x_top"], "right_bottom": edges[0]["x_bottom"]}]
    for index, edge in enumerate(edges):
        following = edges[index + 1] if index + 1 < len(edges) else None
        candidate_id = int(edge["column"]["column_id"])
        specs.append({
            "role": column_roles.get(candidate_id, f"Amount {index + 1}"),
            "candidate": candidate_id,
            "left_top": edge["x_top"], "left_bottom": edge["x_bottom"],
            "right_top": following["x_top"] if following else width,
            "right_bottom": following["x_bottom"] if following else width,
            "sparse": not bool(edge["column"].get("recurring", True)),
        })
    sections = []
    for section_id, spec in enumerate(specs):
        polygon = [[spec["left_top"], 0.0], [spec["right_top"], 0.0],
                   [spec["right_bottom"], height], [spec["left_bottom"], height]]
        members = []
        for phrase in phrases:
            x, y = _phrase_center(phrase)
            fraction = y / height if height else 0.0
            left_x = spec["left_top"] + (spec["left_bottom"] - spec["left_top"]) * fraction
            right_x = spec["right_top"] + (spec["right_bottom"] - spec["right_top"]) * fraction
            if left_x <= x < right_x or (section_id == len(specs) - 1 and x == right_x):
                members.append(phrase)
        phrase_ids, token_ids = _source_ids(members)
        sections.append({
            "column_section_id": section_id, "role": spec["role"],
            "polygon": [[round(x, 3), round(y, 3)] for x, y in polygon],
            "bbox": _polygon_bbox(polygon), "phrase_ids": phrase_ids,
            "source_token_ids": token_ids,
            "source_column_candidate_id": spec["candidate"],
            "sparse": bool(spec.get("sparse")),
            "left_boundary_source": label_left_source if spec["candidate"] is None else "amount_left_edge",
            "right_boundary_source": "page_right" if section_id == len(specs) - 1 else "next_amount_left_edge",
        })
    findings = [] if main_labels else [{"code": "no_main_text_anchor", "severity": "review"}]
    return sections, findings


def _alignment_boundaries(geometry: dict[str, Any], width: float) -> list[dict[str, Any]]:
    grouped: dict[int, list[tuple[int, int, list[float]]]] = {}
    for fit in geometry.get("fit_candidates") or []:
        column_id = int(fit["column_id"])
        for pair, segment in zip(fit.get("pair_phrase_ids") or [], fit.get("segments") or []):
            label_phrase_id, amount_phrase_id = map(int, pair)
            grouped.setdefault(label_phrase_id, []).append(
                (column_id, amount_phrase_id, list(map(float, segment))))

    boundaries = []
    for label_phrase_id, observations in grouped.items():
        y_left = _median([_line_y(segment, 0.0) for _, _, segment in observations])
        y_right = _median([_line_y(segment, width) for _, _, segment in observations])
        boundaries.append({
            "boundary_id": -1, "kind": "alignment_fit",
            "label_phrase_id": label_phrase_id,
            "amount_phrase_ids": sorted({amount for _, amount, _ in observations}),
            "column_candidate_ids": sorted({column for column, _, _ in observations}),
            "n_observations": len(observations),
            "line_segment": [0.0, round(y_left, 3), width, round(y_right, 3)],
            "sort_y": (y_left + y_right) / 2,
        })
    boundaries.sort(key=lambda boundary: (boundary["sort_y"], boundary["label_phrase_id"]))
    for boundary_id, boundary in enumerate(boundaries):
        boundary["boundary_id"] = boundary_id
        boundary.pop("sort_y")
    return boundaries


def _main_text_boundaries(geometry: dict[str, Any], width: float,
                          wrap_direction: str, *, first_band_id: int | None = None,
                          last_band_id: int | None = None,
                          top_gutter_y: float = 0.0) -> list[dict[str, Any]]:
    phrases = {int(phrase["phrase_id"]): phrase
               for phrase in geometry.get("phrases") or []}
    bands = {int(band["band_id"]): band
             for band in geometry.get("baseline_bands") or []}
    boundaries = []
    for phrase in phrases.values():
        if phrase.get("text_candidate_type") != "main_text_candidate":
            continue
        if float(phrase["bbox"][3]) <= top_gutter_y:
            continue
        if first_band_id is not None and int(phrase["band_id"]) < first_band_id:
            continue
        if last_band_id is not None and int(phrase["band_id"]) > last_band_id:
            continue
        band = bands.get(int(phrase["band_id"]))
        if not band:
            continue
        baseline_segment = list(map(float, band.get("baseline_segment") or
                                    [0.0, band["baseline_y"], width, band["baseline_y"]]))
        if wrap_direction == "wraps_down":
            # PAP rows own their first line and everything below it until the
            # next first line. Anchor the boundary at the main label phrase's
            # bbox top while preserving the band's fitted slope across the
            # page. Using the baseline itself would start the cell at the
            # phrase bottom and geometrically clip its first line.
            phrase_center_x = (float(phrase["bbox"][0]) + float(phrase["bbox"][2])) / 2
            vertical_shift = (float(phrase["bbox"][1])
                              - _line_y(baseline_segment, phrase_center_x))
            segment = [0.0, _line_y(baseline_segment, 0.0) + vertical_shift,
                       width, _line_y(baseline_segment, width) + vertical_shift]
            source = "main_text_candidate_phrase_top"
        else:
            segment = baseline_segment
            source = "main_text_candidate_band_baseline"
        boundaries.append({
            "boundary_id": -1, "kind": "main_text_boundary",
            "band_id": int(phrase["band_id"]),
            "label_phrase_id": int(phrase["phrase_id"]),
            "amount_phrase_ids": [int(value) for value in
                                  phrase.get("aligned_amount_phrase_ids") or []],
            "line_segment": [round(value, 3) for value in segment],
            "sort_y": _line_y(segment, width / 2),
            "wrap_direction": wrap_direction,
            "source": source,
        })
    boundaries.sort(key=lambda boundary: (boundary["sort_y"], boundary["label_phrase_id"]))
    for boundary_id, boundary in enumerate(boundaries):
        boundary["boundary_id"] = boundary_id
        boundary.pop("sort_y")
    return boundaries


def _row_sections(geometry: dict[str, Any], phrases: list[dict[str, Any]], *,
                  root_band_id: int | None, root_source: str,
                  wrap_direction: str, first_band_id: int | None = None,
                  last_band_id: int | None = None,
                  top_gutter_y: float = 0.0) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    width, height = map(float, geometry.get("page_size_pt") or [720.0, 864.0])
    bands = {int(band["band_id"]): band for band in geometry.get("baseline_bands") or []}
    findings = []
    if root_band_id is not None and root_band_id in bands:
        root = bands[root_band_id]
        root_segment = root.get("baseline_segment") or [0.0, root["baseline_y"], width, root["baseline_y"]]
        top = [0.0, round(_line_y(root_segment, 0.0), 3),
               width, round(_line_y(root_segment, width), 3)]
    else:
        top = [0.0, 0.0, width, 0.0]
        if root_band_id is not None:
            findings.append({"code": "reviewed_root_band_missing", "severity": "review",
                             "band_id": root_band_id})
            root_source = "page_top_fallback"

    main_boundaries = _main_text_boundaries(
        geometry, width, wrap_direction, first_band_id=first_band_id,
        last_band_id=last_band_id, top_gutter_y=top_gutter_y)
    if not main_boundaries:
        return [], [], findings + [{"code": "no_main_text_boundaries", "severity": "review"}]
    if wrap_direction == "wraps_down":
        boundaries = [*main_boundaries,
                      {"boundary_id": "page_bottom", "kind": "page_bottom",
                       "line_segment": [0.0, height, width, height], "source": "page_geometry"}]
    else:
        if wrap_direction != "wraps_up":
            findings.append({"code": "unclassified_row_wrap_direction", "severity": "review"})
        root_y = _line_y(top, width / 2)
        main_boundaries = [boundary for boundary in main_boundaries
                           if _line_y(boundary["line_segment"], width / 2) > root_y + 0.5]
        boundaries = [{"boundary_id": "root", "kind": "root",
                       "band_id": root_band_id if root_band_id in bands else None,
                       "line_segment": top, "source": root_source},
                      *main_boundaries]
        if last_band_id is None:
            boundaries.append({"boundary_id": "page_bottom", "kind": "page_bottom",
                               "line_segment": [0.0, height, width, height],
                               "source": "page_geometry"})

    sections = []
    phrase_by_id = {int(phrase["phrase_id"]): phrase for phrase in phrases}
    for row_section_id, (upper, lower) in enumerate(zip(boundaries, boundaries[1:])):
        upper_line, lower_line = upper["line_segment"], lower["line_segment"]
        polygon = [[0.0, upper_line[1]], [width, upper_line[3]],
                   [width, lower_line[3]], [0.0, lower_line[1]]]
        members = []
        upper_band = upper.get("band_id")
        lower_band = lower.get("band_id")
        for phrase in phrases:
            if first_band_id is not None and int(phrase["band_id"]) < first_band_id:
                continue
            if last_band_id is not None and int(phrase["band_id"]) > last_band_id:
                continue
            phrase_band = int(phrase["band_id"])
            if wrap_direction == "wraps_down":
                owned = ((upper_band is None or phrase_band >= int(upper_band))
                         and (lower_band is None or phrase_band < int(lower_band)))
            else:
                owned = ((upper_band is None or phrase_band > int(upper_band))
                         and (lower_band is None or phrase_band <= int(lower_band)))
            if owned:
                members.append(phrase)
        phrase_ids, token_ids = _source_ids(members)
        anchor_boundary = upper if wrap_direction == "wraps_down" else lower
        terminal_phrase_id = anchor_boundary.get("label_phrase_id")
        anchor_phrase = phrase_by_id.get(int(terminal_phrase_id)) if terminal_phrase_id is not None else None
        relative = (anchor_phrase or {}).get("relative_anchor") or {}
        raw_left = None if anchor_phrase is None else float(anchor_phrase["bbox"][0])
        label_left_segment = None
        if raw_left is not None:
            label_left_segment = [round(raw_left, 3), upper_line[1],
                                  round(raw_left, 3), lower_line[1]]
        sections.append({
            "row_section_id": row_section_id,
            "top_boundary_id": upper["boundary_id"],
            "bottom_boundary_id": lower["boundary_id"],
            "polygon": [[round(x, 3), round(y, 3)] for x, y in polygon],
            "bbox": _polygon_bbox(polygon), "phrase_ids": phrase_ids,
            "source_token_ids": token_ids,
            "row_wrap_direction": wrap_direction,
            "label_left_boundary": None if raw_left is None else {
                "source": "main_text_bbox_left",
                "terminal_label_phrase_id": int(terminal_phrase_id),
                "anchor_distance": relative.get("distance_pt"),
                "line_segment": label_left_segment,
            },
        })
    return boundaries, sections, findings


def _cell_sections(columns: list[dict[str, Any]], rows: list[dict[str, Any]],
                   phrases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    phrase_by_id = {int(phrase["phrase_id"]): phrase for phrase in phrases}
    cells = []
    for row in rows:
        row_ids = set(map(int, row["phrase_ids"]))
        row_polygon = row["polygon"]
        top = [*row_polygon[0], *row_polygon[1]]
        bottom = [*row_polygon[3], *row_polygon[2]]
        row["left_of_label_phrase_ids"] = []
        row["left_of_label_token_ids"] = []
        if row.get("label_left_boundary"):
            label_left = list(map(float, row["label_left_boundary"]["line_segment"]))
            prefix_phrases = [
                phrase_by_id[phrase_id] for phrase_id in row_ids
                if _phrase_center(phrase_by_id[phrase_id])[0]
                < _line_x(label_left, _phrase_center(phrase_by_id[phrase_id])[1])
            ]
            row["left_of_label_phrase_ids"], row["left_of_label_token_ids"] = _source_ids(prefix_phrases)
        for column in columns:
            column_ids = set(map(int, column["phrase_ids"]))
            column_polygon = column["polygon"]
            left = [*column_polygon[0], *column_polygon[3]]
            if column["role"] == "Labels" and row.get("label_left_boundary"):
                left = list(map(float, row["label_left_boundary"]["line_segment"]))
            right = [*column_polygon[1], *column_polygon[2]]
            polygon = [_intersection(left, top), _intersection(right, top),
                       _intersection(right, bottom), _intersection(left, bottom)]
            members = [phrase_by_id[phrase_id] for phrase_id in row_ids & column_ids]
            if column["role"] == "Labels":
                accepted_observations = {"text_candidate", "mixed_candidate"}
                content_source = "text_or_mixed_candidate"
            else:
                accepted_observations = {"money_candidate"}
                content_source = "money_candidate"
            members = [phrase for phrase in members
                       if phrase.get("observation") in accepted_observations]
            members.sort(key=lambda phrase: (int(phrase.get("band_id", -1)),
                                              float(phrase["bbox"][0]),
                                              int(phrase["phrase_id"])))
            line_groups: dict[int, list[dict[str, Any]]] = {}
            for phrase in members:
                line_groups.setdefault(int(phrase.get("band_id", -1)), []).append(phrase)
            lines = []
            for band_id, line_phrases in line_groups.items():
                line_phrases.sort(key=lambda phrase: float(phrase["bbox"][0]))
                lines.append({
                    "band_id": band_id,
                    "phrase_ids": [int(phrase["phrase_id"]) for phrase in line_phrases],
                    "text": " ".join(str(phrase.get("text") or "") for phrase in line_phrases).strip(),
                })
            phrase_ids, token_ids = _source_ids(members)
            cells.append({
                "cell_section_id": len(cells),
                "row_section_id": int(row["row_section_id"]),
                "column_section_id": int(column["column_section_id"]),
                "column_role": column["role"],
                "polygon": polygon, "bbox": _polygon_bbox(polygon),
                "phrase_ids": phrase_ids, "source_token_ids": token_ids,
                "content_source": content_source,
                "lines": lines,
                "text": "\n".join(line["text"] for line in lines if line["text"]),
                "flat_text": " ".join(line["text"] for line in lines if line["text"]),
                "empty": not bool(token_ids),
            })
    return cells


def _cardinality_findings(rows: list[dict[str, Any]], cells: list[dict[str, Any]],
                          phrases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Flag ambiguous row/cell contents without attempting semantic repair."""
    phrase_by_id = {int(phrase["phrase_id"]): phrase for phrase in phrases}
    findings = []
    for row in rows:
        main_ids = [int(phrase_id) for phrase_id in row.get("phrase_ids") or []
                    if phrase_by_id[int(phrase_id)].get("text_candidate_type")
                    == "main_text_candidate"]
        if len(main_ids) > 1:
            findings.append({
                "code": "multiple_main_text_candidates_in_row", "severity": "review",
                "row_section_id": int(row["row_section_id"]),
                "phrase_ids": main_ids,
            })
    for cell in cells:
        members = [phrase_by_id[int(phrase_id)]
                   for phrase_id in cell.get("phrase_ids") or []]
        main_ids = [int(phrase["phrase_id"]) for phrase in members
                    if phrase.get("text_candidate_type") == "main_text_candidate"]
        money_ids = [int(phrase["phrase_id"]) for phrase in members
                     if phrase.get("observation") == "money_candidate"]
        common = {
            "severity": "review",
            "cell_section_id": int(cell["cell_section_id"]),
            "row_section_id": int(cell["row_section_id"]),
            "column_section_id": int(cell["column_section_id"]),
            "column_role": cell["column_role"],
        }
        if len(main_ids) > 1:
            findings.append({**common,
                             "code": "multiple_main_text_candidates_in_cell",
                             "phrase_ids": main_ids})
        if len(money_ids) > 1:
            findings.append({**common,
                             "code": "multiple_money_candidates_in_cell",
                             "phrase_ids": money_ids})
        if main_ids and cell["column_role"] != "Labels":
            findings.append({**common,
                             "code": "main_text_candidate_outside_label_cell",
                             "phrase_ids": main_ids})
    return findings


FLAG_MESSAGES = {
    "multiple_main_text_candidates_in_row": "Row contains more than one main label candidate.",
    "multiple_main_text_candidates_in_cell": "Label cell contains more than one main label candidate.",
    "multiple_money_candidates_in_cell": "Amount cell contains more than one money candidate.",
    "main_text_candidate_outside_label_cell": "Main label candidate was assigned outside the label column.",
    "no_recurring_amount_column": "No amount-column anchor was detected.",
    "no_main_text_anchor": "No main label anchor was available for the label column.",
    "reviewed_root_band_missing": "The reviewed root band is absent from current geometry.",
    "no_main_text_boundaries": "No main label boundaries were available for row construction.",
    "unclassified_row_wrap_direction": "The row wrap direction is not classified.",
}


def _flagged_objects(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    flags = []
    for flag_id, finding in enumerate(findings):
        if finding.get("cell_section_id") is not None:
            object_type, object_id = "cell_section", int(finding["cell_section_id"])
        elif finding.get("row_section_id") is not None:
            object_type, object_id = "row_section", int(finding["row_section_id"])
        elif finding.get("column_section_id") is not None:
            object_type, object_id = "column_section", int(finding["column_section_id"])
        elif finding.get("band_id") is not None:
            object_type, object_id = "band", int(finding["band_id"])
        else:
            object_type, object_id = "page", None
        flags.append({
            "flag_id": flag_id,
            "code": str(finding["code"]),
            "severity": str(finding.get("severity") or "review"),
            "object_type": object_type,
            "object_id": object_id,
            "message": FLAG_MESSAGES.get(str(finding["code"]), str(finding["code"])),
            **{key: value for key, value in finding.items()
               if key not in {"code", "severity"}},
        })
    return flags


def derive_table_sections(geometry: dict[str, Any], *, root_band_id: int | None = None,
                          root_source: str = "page_top",
                          column_roles: dict[int, str] | None = None,
                          header_specs: list[dict[str, Any]] | None = None,
                          table_type: str = "by_ou",
                          wrap_direction: str = "wraps_up",
                          layout_source: str = "caller_default",
                          first_band_id: int | None = None,
                          last_band_id: int | None = None) -> dict[str, Any]:
    all_phrases = [phrase for phrase in geometry.get("phrases") or [] if phrase.get("bbox")]
    page_height = float((geometry.get("page_size_pt") or [720.0, 864.0])[1])
    top_gutter_y = min(TOP_GUTTER_Y_PT, page_height * 0.055)
    excluded_top_gutter = [phrase for phrase in all_phrases
                           if float(phrase["bbox"][3]) <= top_gutter_y]
    phrases = [phrase for phrase in all_phrases
               if float(phrase["bbox"][3]) > top_gutter_y]
    headers = _header_sections(geometry, all_phrases, header_specs or [])
    columns, column_findings = _column_sections(
        geometry, phrases, column_roles or {}, first_band_id=first_band_id,
        last_band_id=last_band_id)
    boundaries, rows, row_findings = _row_sections(
        geometry, phrases, root_band_id=root_band_id, root_source=root_source,
        wrap_direction=wrap_direction, first_band_id=first_band_id,
        last_band_id=last_band_id, top_gutter_y=top_gutter_y)
    cells = _cell_sections(columns, rows, phrases) if columns and rows else []
    cardinality_findings = _cardinality_findings(rows, cells, phrases)
    findings = column_findings + row_findings + cardinality_findings
    flags = _flagged_objects(findings)
    return {
        "algorithm": {"name": "deterministic_table_sections", "version": 9},
        "table_layout": {"table_type": table_type, "wrap_direction": wrap_direction,
                         "source": layout_source, "first_band_id": first_band_id,
                         "last_band_id": last_band_id},
        "header_sections": headers, "column_sections": columns, "row_boundaries": boundaries,
        "row_sections": rows, "cell_sections": cells,
        "top_gutter_exclusion": {
            "bottom_y": round(top_gutter_y, 3),
            "rule": "exclude_phrase_when_bbox_bottom_at_or_above_boundary",
            "phrase_ids": [int(phrase["phrase_id"]) for phrase in excluded_top_gutter],
            "source_token_ids": sorted({int(token_id) for phrase in excluded_top_gutter
                                        for token_id in phrase.get("token_ids") or []}),
        },
        "findings": findings, "flagged_objects": flags,
        "diagnostics": {
            "n_header_sections": len(headers), "n_column_sections": len(columns),
            "n_alignment_boundaries": sum(boundary.get("kind") == "main_text_boundary"
                                           for boundary in boundaries),
            "n_main_text_boundaries": sum(boundary.get("kind") == "main_text_boundary"
                                           for boundary in boundaries),
            "n_row_sections": len(rows),
            "n_cell_sections": len(cells),
            "n_nonempty_cell_sections": sum(not cell["empty"] for cell in cells),
            "n_findings": len(findings), "n_flags": len(flags),
            "n_top_gutter_excluded_phrases": len(excluded_top_gutter),
        },
    }


def run_stage(context, *, seeds_path: Path = DEFAULT_SEEDS) -> dict[str, Any]:
    results = []
    started_at, started = iso_now(), time.perf_counter()
    resolved_seeds = resolve_project_path(seeds_path)
    seeds = read_json(resolved_seeds) if resolved_seeds.is_file() else None
    resolved_layouts = resolve_project_path(DEFAULT_LAYOUTS)
    layouts = read_json(resolved_layouts) if resolved_layouts.is_file() else None
    for page_no in context.pages:
        page_started_at, page_started = iso_now(), time.perf_counter()
        try:
            geometry = read_json(
                context.store.layer_path("token_geometry_repair", page_no))
            root_band_id, root_source, column_roles, header_specs = _reviewed_page_seed(seeds, page_no)
            layout = _page_layout(layouts, page_no)
            first_band_id, last_band_id = _reviewed_band_range(seeds, page_no)
            payload = derive_table_sections(
                geometry, root_band_id=root_band_id, root_source=root_source,
                column_roles=column_roles, header_specs=header_specs,
                table_type=layout["table_type"], wrap_direction=layout["wrap_direction"],
                layout_source=layout["source"], first_band_id=first_band_id,
                last_band_id=last_band_id)
            payload.update({"page": page_no, "page_size_pt": geometry.get("page_size_pt")})
            stamp_meta(payload, stage="layer:table_structure",
                       producer="deterministic_table_sections_v9")
            write_json_atomic(context.store.layer_path("table_structure", page_no), payload)
            result = {"page": page_no, "pass": True, **payload["diagnostics"]}
        except Exception as error:
            result = {"page": page_no, "pass": False,
                      "error_type": type(error).__name__, "error": str(error)}
        result.update({"started_at": page_started_at, "completed_at": iso_now(),
                       "timestamp_source": "captured",
                       "elapsed_s": round(time.perf_counter() - page_started, 3)})
        results.append(result)
    n_fail = sum(not result["pass"] for result in results)
    n_flags = sum(int(result.get("n_flags") or 0) for result in results)
    summary = {"artifact_version": 1, "gate": "TABLE_GEOMETRIC_SECTIONS",
               "name": "deterministic_table_sections", "scope": "geometry_only_v9",
               "n_pages": len(results), "n_fail": n_fail,
               "n_flags": n_flags,
               "n_flagged_pages": sum(int(result.get("n_flags") or 0) > 0
                                      for result in results),
               "started_at": started_at, "completed_at": iso_now(),
               "timestamp_source": "captured",
               "elapsed_s": round(time.perf_counter() - started, 3),
               "pages": results, "pass": n_fail == 0}
    write_json_atomic(context.store.stage_qa_path("table_structure"), summary)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    add_stage_arguments(parser)
    summary = run_stage(make_context(parser.parse_args()))
    print(f"002.20 Table geometry: pages={summary['n_pages']} fail={summary['n_fail']} "
          f"elapsed={summary['elapsed_s']}s")
    require_pass(summary)


if __name__ == "__main__":
    main()
