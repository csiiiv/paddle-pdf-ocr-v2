#!/usr/bin/env python3
"""Stage 002.30: deterministic By-OU hierarchy tree for table exploration.

Inputs: 002.20-table-structure/pages/*.json, 002.10-token-geometry/pages/*.json,
and reviewed By-OU seeds plus layout spans
Outputs: 002.30-by-ou-tree/tree.json, pages/*.json, and qa/summary.json

This stage realizes the reviewed table-hierarchy procedure in
docs/TABLE_HIERARCHY_BIN_CALIBRATION.md for the By-OU table: per-page
distance-cluster fitting, program-code discrimination at the shared parent
indent, semantic exclusions (subtotals, funding metadata), section headers,
and cross-page parent carry. It emits one viewer-ready tree per table.
"""
from __future__ import annotations

import argparse
import re
import statistics
import time
from pathlib import Path
from typing import Any

from _common import add_stage_arguments, make_context, require_pass, resolve_project_path
from _shared.artifacts import read_json, write_json_atomic
from _shared.contracts import stamp_meta
from _shared.prexc import CODE_LENGTH, apply_prexc_hierarchy, compute_prexc_parents, is_prexc_code
from _shared.timestamps import iso_now

DEFAULT_SEEDS = Path("fixtures/by_ou_table_seeds.json")
DEFAULT_LAYOUTS = Path("fixtures/table_layout_spans.json")

SECTION_DISTANCE_MIN_PT = 540.0
CENTER_TOLERANCE_PT = 4.0
CLUSTER_SPLIT_GAP_PT = 8.0
SINGLE_CLUSTER_MIDPOINT_PT = 466.5
# CODE_LENGTH imported from _shared.prexc (15-digit PREXC / UACS P/A/P).

FUNDING_LABELS = {"GOP", "GOP Counterpart", "Loan Proceeds"}
PAGE_HEADER_TEXT = re.compile(r"^\d+\s+EXPENDITURE PROGRAM\b", re.IGNORECASE)
LETTER_SECTION = re.compile(r"^([A-Z])\.\s+(.+)$", re.IGNORECASE)
NUMBERED_SUBSECTION = re.compile(r"^([A-Z])\.(\d+)\s+(.+)$", re.IGNORECASE)
REGION_TEXT = re.compile(
    r"Region\s+[IVX]+[A-Z]*\b|National Capital Region|\(NCR\)|"
    r"Administrative Region|\(CAR\)|Island Region|\(NIR\)", re.IGNORECASE)
SUBTOTAL_TEXT = re.compile(r"^sub[\s-]*total\b", re.IGNORECASE)
TOTAL_TEXT = re.compile(r"^total\b", re.IGNORECASE)

CODED_KINDS = {"program", "activity"}
PARENT_KINDS = {"program", "activity", "region", "office", "section", "subsection"}

REVIEW_FLAG_CODES = {
    "outside_center_tolerance", "weak_page_fit", "extra_distance_cluster",
    "parent_carry_missing", "carry_gap_reset", "subtotal_parent_unmatched",
    "suspect_leading_continuation", "row_without_anchor_distance",
    "unclassified_distance", "activity_without_program_parent",
    "multiple_money_candidates_in_cell", "multiple_main_text_candidates_in_row",
    "main_text_candidate_outside_label_cell", "no_distance_clusters",
}
INFO_FLAG_CODES = {"continuation_merged", "funding_metadata_excluded"}

FLAG_MESSAGES = {
    "outside_center_tolerance": "Row distance exceeds the ±4 pt center tolerance.",
    "weak_page_fit": "Page distance fit used fewer than two supported clusters.",
    "extra_distance_cluster": "Page fit found more than two clusters; extras merged into the office tier.",
    "no_distance_clusters": "Page had no fittable body-row distances.",
    "parent_carry_missing": "Row starts a requested page range without carried parent context.",
    "carry_gap_reset": "Parent carry was reset at a page gap per reviewed carry policy.",
    "subtotal_parent_unmatched": "Sub-total label matched no earlier row; attached to the open section.",
    "suspect_leading_continuation": "Label begins with a wrap fragment such as 'Office'.",
    "row_without_anchor_distance": "Row has amounts but no anchor distance for its label.",
    "unclassified_distance": "Row distance could not be assigned to a fitted center.",
    "activity_without_program_parent": "Coded activity row has no preceding program with the same code prefix.",
    "continuation_merged": "Continuation fragment row was merged into the previous row.",
    "funding_metadata_excluded": "Funding metadata row is excluded from the hierarchy.",
    "multiple_money_candidates_in_cell": "Inherited from stage 002.20: ambiguous amount cell.",
    "multiple_main_text_candidates_in_row": "Inherited from stage 002.20: ambiguous row label.",
    "main_text_candidate_outside_label_cell": "Inherited from stage 002.20: label candidate outside label column.",
}


def _median(values: list[float]) -> float:
    return float(statistics.median(values))


def _clean_text(text: str) -> str:
    return " ".join(str(text or "").split())


def _amount_value(text: str) -> int | None:
    digits = re.sub(r"\D", "", _clean_text(text))
    return int(digits) if digits else None


def _norm_label(text: str) -> str:
    lowered = str(text or "").lower()
    lowered = re.sub(r"\(\s*s\s*\)", " ", lowered)
    section = NUMBERED_SUBSECTION.match(lowered.strip())
    if section:
        lowered = section.group(3)
    else:
        letter = LETTER_SECTION.match(lowered.strip())
        if letter:
            lowered = letter.group(2)
    lowered = re.sub(r"[^a-z0-9]+", " ", lowered)
    return " ".join(lowered.split())


def _code_kind(code: str) -> str | None:
    code = str(code or "").strip()
    if not is_prexc_code(code):
        return None
    return "program" if code[6:] == "0" * (CODE_LENGTH - 6) else "activity"


def _fit_page_centers(distances: list[float]) -> tuple[dict[str, float | None], list[dict[str, Any]]]:
    """Split page-local label distances into region/office centers.

    Distances are the shared By-OU parent and office clusters from the
    calibration profile; coded rows are excluded by the caller because their
    tier is fixed by the program-code discriminator.
    """
    if not distances:
        return {"region": None, "office": None}, [
            {"code": "no_distance_clusters", "severity": "review"}]
    ordered = sorted(distances, reverse=True)
    groups: list[list[float]] = [[ordered[0]]]
    for distance in ordered[1:]:
        if groups[-1][-1] - distance > CLUSTER_SPLIT_GAP_PT:
            groups.append([distance])
        else:
            groups[-1].append(distance)
    flags: list[dict[str, Any]] = []
    if len(groups) == 1:
        center = _median(groups[0])
        centers = ({"region": center, "office": None} if center >= SINGLE_CLUSTER_MIDPOINT_PT
                   else {"region": None, "office": center})
        flags.append({"code": "weak_page_fit", "severity": "review",
                      "n_observations": len(ordered)})
    else:
        centers = {"region": _median(groups[0]),
                   "office": _median([value for group in groups[1:] for value in group])}
        if len(groups) > 2:
            flags.append({"code": "extra_distance_cluster", "severity": "review",
                          "n_clusters": len(groups)})
    return centers, flags


def _row_view(row: dict[str, Any], structure: dict[str, Any],
              phrases: dict[int, dict[str, Any]]) -> dict[str, Any] | None:
    """Collect label, amounts, code, and evidence for one row section."""
    row_id = int(row["row_section_id"])
    cells = [cell for cell in structure.get("cell_sections") or []
             if int(cell["row_section_id"]) == row_id]
    label_cell = next((cell for cell in cells if cell["column_role"] == "Labels"), None)
    label_text = _clean_text((label_cell or {}).get("text") or "")
    amounts: dict[str, dict[str, Any]] = {}
    total: dict[str, Any] | None = None
    for cell in sorted((cell for cell in cells if cell["column_role"] != "Labels"),
                       key=lambda cell: int(cell["column_section_id"])):
        text = _clean_text(cell.get("text") or "")
        if not text:
            continue
        n_money = len(cell.get("phrase_ids") or [])
        value = _amount_value(text) if n_money <= 1 else None
        entry = {"text": text, "value": value, "role": cell["column_role"]}
        amounts[cell["column_role"]] = entry
        total = entry
    left_ids = [int(value) for value in row.get("left_of_label_phrase_ids") or []]
    code = next((str(phrases[value]["text"]).strip() for value in left_ids
                 if value in phrases and phrases[value].get("observation") == "code_candidate"), None)
    boundary = row.get("label_left_boundary") or {}
    terminal_id = boundary.get("terminal_label_phrase_id")
    terminal = phrases.get(int(terminal_id)) if terminal_id is not None else None
    has_amounts = bool(amounts)
    if not label_text and not has_amounts:
        return None
    return {
        "row_section_id": row_id,
        "label_text": label_text,
        "label_lines": [(line.get("band_id"), _clean_text(line.get("text") or ""))
                        for line in (label_cell or {}).get("lines") or []],
        "label_phrase_ids": [int(value) for value in (label_cell or {}).get("phrase_ids") or []],
        "phrase_ids": [int(value) for value in row.get("phrase_ids") or []],
        "token_ids": sorted({int(token) for value in row.get("phrase_ids") or []
                             for token in (phrases.get(int(value)) or {}).get("token_ids") or []}),
        "amounts": amounts,
        "total": total,
        "code": code,
        "distance": boundary.get("anchor_distance"),
        "terminal_phrase_id": terminal_id,
        "terminal_distance": (terminal or {}).get("relative_anchor", {}).get("distance_pt")
                             if terminal else None,
        "bbox": row.get("bbox"),
    }


def _embedded_sections(view: dict[str, Any], phrases: dict[int, dict[str, Any]]) -> list[dict[str, Any]]:
    """Section-header phrases carried inside a body row's phrase set."""
    found = []
    for phrase_id in view["phrase_ids"]:
        phrase = phrases.get(phrase_id)
        if not phrase:
            continue
        distance = (phrase.get("relative_anchor") or {}).get("distance_pt")
        text = _clean_text(phrase.get("text") or "")
        if distance is None or distance < SECTION_DISTANCE_MIN_PT:
            continue
        if phrase.get("observation") not in {"text_candidate", "mixed_candidate"}:
            continue
        if PAGE_HEADER_TEXT.match(text) or SUBTOTAL_TEXT.match(text) or TOTAL_TEXT.match(text):
            continue
        found.append({"phrase_id": phrase_id, "band_id": int(phrase.get("band_id", -1)),
                      "text": text, "distance": float(distance)})
    found.sort(key=lambda item: item["band_id"])
    return found


def _tier_for_distance(distance: float | None, centers: dict[str, float | None]) -> tuple[int | None, float | None, str]:
    if distance is None:
        return None, None, "row_without_anchor_distance"
    options = [(tier, center) for tier, center in
               ((1, centers.get("region")), (2, centers.get("office"))) if center is not None]
    if not options:
        return None, None, "no_distance_clusters"
    tier, center = min(options, key=lambda item: abs(distance - item[1]))
    return tier, center, ""


class TreeBuilder:
    """Accumulates nodes in document order with a carried parent stack."""

    def __init__(self, table_seed: dict[str, Any], title: str):
        self.table_seed = table_seed
        self.nodes: dict[str, dict[str, Any]] = {}
        self.order: list[str] = []
        self.label_matches: list[tuple[str, str]] = []
        self.sections_by_letter: dict[str, str] = {}
        self.program_by_prefix: dict[str, str] = {}
        self.stack: list[tuple[int, str]] = [(0, "root")]
        self.page_flags: dict[int, list[dict[str, Any]]] = {}
        self.page_nodes: dict[int, list[str]] = {}
        self.tier_fits: dict[int, dict[str, Any]] = {}
        self.column_roles: dict[int, list[dict[str, Any]]] = {}
        self.row_counts: dict[int, int] = {}
        root_label = title or str(table_seed.get("table_id") or "By-OU table")
        self.emit({"id": "root", "parent": None, "kind": "table_root", "tier": 0,
                   "label": root_label, "children": [], "flags": [], "page": None})

    def flag(self, page: int, flag_code: str, **details: Any) -> None:
        severity = "info" if flag_code in INFO_FLAG_CODES else "review"
        entry = {"code": flag_code, "severity": severity,
                 "message": FLAG_MESSAGES.get(flag_code, flag_code)}
        entry.update({key: value for key, value in details.items()
                      if value is not None and key not in {"severity", "message"}})
        self.page_flags.setdefault(page, []).append(entry)

    def emit(self, node: dict[str, Any]) -> str:
        node.setdefault("flags", [])
        node["children"] = []
        self.nodes[node["id"]] = node
        self.order.append(node["id"])
        parent_id = node.get("parent")
        if parent_id and parent_id in self.nodes:
            self.nodes[parent_id]["children"].append(node["id"])
        return node["id"]

    def top(self) -> tuple[int, str]:
        return self.stack[-1]

    def open_section_id(self) -> str:
        for tier, node_id in reversed(self.stack):
            if tier == 0:
                return node_id
        return "root"

    def resolve_body_parent(self, tier: int) -> str:
        """Collapse the stack for a body row and return its parent id."""
        if tier == 1:
            while self.stack and self.top()[0] >= 2:
                self.stack.pop()
            top_tier, top_id = self.top()
            if top_tier == 1:
                top_kind = self.nodes[top_id]["kind"]
                if top_kind in CODED_KINDS:
                    return top_id
                self.stack.pop()
                return self.nodes[top_id]["parent"]
            return top_id
        while self.stack and self.top()[0] >= 2:
            self.stack.pop()
        return self.top()[1]

    def build_page(self, page: int, geometry: dict[str, Any], structure: dict[str, Any],
                   *, first_page_of_table: bool, previous_page: int | None) -> None:
        phrases = {int(phrase["phrase_id"]): phrase
                   for phrase in geometry.get("phrases") or []}
        findings_by_row: dict[int, list[dict[str, Any]]] = {}
        for finding in structure.get("findings") or []:
            if finding.get("row_section_id") is not None:
                findings_by_row.setdefault(int(finding["row_section_id"]), []).append(finding)
        self.column_roles[page] = [
            {"role": column["role"], "column_section_id": int(column["column_section_id"])}
            for column in structure.get("column_sections") or []]

        if previous_page is not None and page != previous_page + 1:
            self.stack = [(0, "root")]
            self.sections_by_letter.clear()
            self.flag(page, "carry_gap_reset", from_page=previous_page)
        if first_page_of_table:
            seed = self.table_seed.get("hierarchy_seed") or {}
            seed_page = int(seed.get("page", -1))
            if seed_page == page:
                self.emit_section(page, phrases.get(int(seed.get("phrase_id", -1))),
                                  seed_text=str(seed.get("text") or ""), via_seed=True)
            elif previous_page is None:
                self.flag(page, "parent_carry_missing", reason="table_start_page_not_requested")

        views = []
        for row in structure.get("row_sections") or []:
            view = _row_view(row, structure, phrases)
            if view is not None:
                views.append(view)
        self.row_counts[page] = len(views)

        fit_distances = []
        for view in views:
            if view["code"] is not None or view["distance"] is None:
                continue
            if view["terminal_distance"] is not None and view["terminal_distance"] >= SECTION_DISTANCE_MIN_PT:
                continue
            if view["label_text"] in FUNDING_LABELS:
                continue
            fit_distances.append(float(view["distance"]))
        centers, fit_flags = _fit_page_centers(fit_distances)
        for entry in fit_flags:
            self.flag(page, entry["code"], **{key: value for key, value in entry.items()
                                              if key not in {"code", "severity"}})
        self.tier_fits[page] = {
            "region_center": centers["region"], "office_center": centers["office"],
            "tolerance_pt": CENTER_TOLERANCE_PT, "cluster_split_gap_pt": CLUSTER_SPLIT_GAP_PT,
            "n_observations": len(fit_distances)}

        for view in views:
            for header in _embedded_sections(view, phrases):
                self.emit_section(page, {**phrases.get(header["phrase_id"], {}),
                                         "phrase_id": header["phrase_id"],
                                         "band_id": header["band_id"],
                                         "text": header["text"]},
                                  seed_text=header["text"], via_seed=False,
                                  distance=header["distance"])
            self.build_row(page, view, centers, findings_by_row.get(view["row_section_id"]) or [])

    def emit_section(self, page: int, phrase: dict[str, Any] | None, *, seed_text: str,
                     via_seed: bool, distance: float | None = None) -> str:
        text = _clean_text((phrase or {}).get("text") or seed_text)
        phrase_id = (phrase or {}).get("phrase_id")
        node_id = f"p{page}:ph{phrase_id}" if phrase_id is not None else f"p{page}:sec:{_norm_label(text)[:24]}"
        if node_id in self.nodes:
            return node_id
        subsection = NUMBERED_SUBSECTION.match(text)
        parent_id = "root"
        kind = "section"
        if subsection:
            kind = "subsection"
            parent_id = self.sections_by_letter.get(subsection.group(1).upper(), "root")
        else:
            letter = LETTER_SECTION.match(text)
            if letter:
                self.sections_by_letter[letter.group(1).upper()] = node_id
        node = {"id": node_id, "parent": parent_id, "kind": kind, "tier": 0,
                "label": text, "page": page, "distance": distance,
                "source": "reviewed_seed" if via_seed else "embedded_section_header",
                "phrase_ids": [int(phrase_id)] if phrase_id is not None else [],
                "amounts": {}, "total": None, "code": None,
                "row_section_id": None}
        self.emit(node)
        self.label_matches.append((_norm_label(text), node_id))
        self.page_nodes.setdefault(page, []).append(node_id)
        self.stack = [(0, node_id)]
        return node_id

    def build_row(self, page: int, view: dict[str, Any], centers: dict[str, float | None],
                  findings: list[dict[str, Any]]) -> None:
        node_flags: list[str] = []
        for finding in findings:
            if finding.get("code") in REVIEW_FLAG_CODES:
                node_flags.append(str(finding["code"]))
                self.flag(page, str(finding["code"]),
                          row_section_id=view["row_section_id"],
                          phrase_ids=finding.get("phrase_ids"))
        label = view["label_text"]
        node_id = f"p{page}:r{view['row_section_id']}"

        if view["distance"] is None and not view["amounts"] and label:
            previous_id = self.order[-1] if self.order else None
            if previous_id and previous_id in self.nodes and self.nodes[previous_id].get("row_section_id") is not None:
                previous = self.nodes[previous_id]
                previous["label"] = _clean_text(f"{previous['label']} {label}")
                previous["label_phrase_ids"] = sorted(set(previous["label_phrase_ids"] + view["label_phrase_ids"]))
                previous["flags"].append("continuation_merged")
                self.flag(page, "continuation_merged", row_section_id=view["row_section_id"],
                          merged_into=previous_id)
                return
        if SUBTOTAL_TEXT.match(label):
            self.emit_subtotal(page, view, node_id, node_flags)
            return
        if TOTAL_TEXT.match(label) and view["terminal_distance"] is not None \
                and view["terminal_distance"] >= SECTION_DISTANCE_MIN_PT:
            node = self._body_node(node_id, page, view, kind="grand_total", tier=0,
                                   center=None, confidence="semantic", flags=node_flags)
            node["parent"] = "root"
            self.emit(node)
            self.label_matches.append((_norm_label(label), node_id))
            self.page_nodes.setdefault(page, []).append(node_id)
            return
        if label in FUNDING_LABELS:
            while self.stack and self.top()[0] >= 2:
                self.stack.pop()
            node = self._body_node(node_id, page, view, kind="funding", tier=2,
                                   center=None, confidence="semantic", flags=node_flags + ["funding_metadata_excluded"])
            node["parent"] = self.top()[1]
            node["excluded"] = True
            self.emit(node)
            self.flag(page, "funding_metadata_excluded", row_section_id=view["row_section_id"])
            self.page_nodes.setdefault(page, []).append(node_id)
            return
        if view["distance"] is None and view["amounts"]:
            node_flags.append("row_without_anchor_distance")
            self.flag(page, "row_without_anchor_distance", row_section_id=view["row_section_id"])

        code_kind = _code_kind(view["code"]) if view["code"] else None
        tier: int
        center: float | None
        confidence = "medium"
        if code_kind is not None:
            tier, center = 1, centers.get("region")
            confidence = "code"
        else:
            fitted_tier, fitted_center, problem = _tier_for_distance(view["distance"], centers)
            tier, center = fitted_tier or 2, fitted_center
            if problem:
                node_flags.append(problem)
                self.flag(page, problem, row_section_id=view["row_section_id"])
            elif center is not None:
                delta = abs(float(view["distance"]) - center)
                if delta > CENTER_TOLERANCE_PT:
                    node_flags.append("outside_center_tolerance")
                    self.flag(page, "outside_center_tolerance", row_section_id=view["row_section_id"],
                              distance=view["distance"], center=round(center, 3))
                confidence = "high" if delta <= 1.5 else "medium"
        if view["label_lines"] and str(view["label_lines"][0][1]).strip().lower() == "office":
            node_flags.append("suspect_leading_continuation")
            self.flag(page, "suspect_leading_continuation", row_section_id=view["row_section_id"])

        if code_kind == "program":
            kind = "program"
        elif code_kind == "activity":
            kind = "activity"
        elif tier == 1:
            kind = "region" if REGION_TEXT.search(label) else "tier1_uncoded"
            if kind == "tier1_uncoded":
                node_flags.append("unclassified_distance")
                self.flag(page, "unclassified_distance", row_section_id=view["row_section_id"],
                          label=label[:48])
        else:
            kind = "office"

        node = self._body_node(node_id, page, view, kind=kind, tier=tier,
                               center=center, confidence=confidence, flags=node_flags)
        if code_kind == "program":
            while self.stack and self.top()[0] >= 1:
                self.stack.pop()
            node["parent"] = self.top()[1]
            self.emit(node)
            self.program_by_prefix[str(view["code"])[:6]] = node_id
            self.stack.append((1, node_id))
        elif code_kind == "activity":
            prefix = str(view["code"])[:6]
            program_id = self.program_by_prefix.get(prefix)
            if program_id and program_id in self.nodes:
                while self.stack and self.top()[0] >= 1 and self.top()[1] != program_id:
                    self.stack.pop()
                node["parent"] = program_id
                self.emit(node)
            else:
                while self.stack and self.top()[0] >= 1:
                    self.stack.pop()
                node["parent"] = self.top()[1]
                self.emit(node)
                node["flags"].append("activity_without_program_parent")
                self.flag(page, "activity_without_program_parent",
                          row_section_id=view["row_section_id"], program_code=view["code"])
            self.stack.append((1, node_id))
        else:
            node["parent"] = self.resolve_body_parent(tier)
            self.emit(node)
            self.stack.append((tier, node_id))
        self.label_matches.append((_norm_label(label), node_id))
        self.page_nodes.setdefault(page, []).append(node_id)

    def emit_subtotal(self, page: int, view: dict[str, Any], node_id: str,
                      node_flags: list[str]) -> None:
        label = view["label_text"]
        target = _norm_label(re.sub(SUBTOTAL_TEXT, "", label, count=1).lstrip(" ,"))
        parent_id: str | None = None
        matched = "none"
        for candidate, candidate_id in reversed(self.label_matches):
            if not candidate:
                continue
            if candidate == target or candidate.rstrip("s") == target.rstrip("s") and (
                    candidate == target + "s" or target == candidate + "s"):
                parent_id = candidate_id
                matched = "label"
                break
        if parent_id is None:
            parent_id = self.open_section_id()
            matched = "open_section"
            node_flags.append("subtotal_parent_unmatched")
            self.flag(page, "subtotal_parent_unmatched", row_section_id=view["row_section_id"],
                      label=label[:48])
        node = self._body_node(node_id, page, view, kind="subtotal", tier=None,
                               center=None, confidence="semantic", flags=node_flags)
        node["parent"] = parent_id
        node["subtotal_match"] = matched
        self.emit(node)
        self.label_matches.append((_norm_label(label), node_id))
        self.page_nodes.setdefault(page, []).append(node_id)

    def _body_node(self, node_id: str, page: int, view: dict[str, Any], *, kind: str,
                   tier: int | None, center: float | None, confidence: str,
                   flags: list[str]) -> dict[str, Any]:
        distance = view["distance"]
        return {
            "id": node_id, "parent": None, "kind": kind, "tier": tier,
            "label": view["label_text"], "code": view["code"],
            "page": page, "row_section_id": view["row_section_id"],
            "phrase_ids": view["phrase_ids"], "label_phrase_ids": view["label_phrase_ids"],
            "token_ids": view["token_ids"], "bbox": view["bbox"],
            "distance": distance, "center": None if center is None else round(center, 3),
            "delta": None if distance is None or center is None else round(abs(float(distance) - center), 3),
            "confidence": confidence, "amounts": view["amounts"], "total": view["total"],
            "flags": flags,
        }


def assemble_tree(page_inputs: list[dict[str, Any]], *, table_seed: dict[str, Any]) -> dict[str, Any]:
    """Build the whole-table tree from ordered per-page geometry and structure."""
    start = table_seed.get("start") or {}
    title = ""
    for entry in page_inputs:
        if int((start.get("page") or -1)) == entry["page"]:
            for header in entry["structure"].get("header_sections") or []:
                if header.get("role") == "table_title":
                    title = _clean_text(header.get("text") or "")
            break
    builder = TreeBuilder(table_seed, title)
    previous_page: int | None = None
    for entry in page_inputs:
        builder.build_page(entry["page"], entry["geometry"], entry["structure"],
                           first_page_of_table=int((start.get("page") or -1)) == entry["page"],
                           previous_page=previous_page)
        previous_page = entry["page"]
    nodes = [builder.nodes[node_id] for node_id in builder.order]
    for node in nodes:
        node["parent_pdf"] = node.get("parent")
    prexc_view = compute_prexc_parents(nodes, synthesize_missing=False)
    for node in nodes:
        node_id = str(node["id"])
        node["parent_prexc"] = prexc_view.get(node_id, node.get("parent_pdf"))
    # Layout pass nests region/office under the open coded row; PREXC then
    # rewires coded parents (and synthesizes missing intermediate shells)
    # while leaving uncoded children attached to those coded rows.
    prexc = apply_prexc_hierarchy(nodes, synthesize_missing=True)
    kind_counts: dict[str, int] = {}
    for node in nodes:
        kind_counts[node["kind"]] = kind_counts.get(node["kind"], 0) + 1
    pages = [entry["page"] for entry in page_inputs]
    tree = {
        "algorithm": {
            "name": "deterministic_by_ou_tree",
            "version": 2,
            "hierarchy": "prexc_code",
            "prexc": prexc,
        },
        "table": {
            "table_id": table_seed.get("table_id"),
            "table_type": table_seed.get("table_type", "by_ou"),
            "reviewed_span": {"start_page": start.get("page"), "end_page": (table_seed.get("end") or {}).get("page")},
            "requested_pages": pages,
            "title": title,
            "carry_policy": table_seed.get("carry_policy") or {},
            "hierarchy_seed": table_seed.get("hierarchy_seed") or {},
        },
        "calibration": {
            "section_distance_min_pt": SECTION_DISTANCE_MIN_PT,
            "center_tolerance_pt": CENTER_TOLERANCE_PT,
            "cluster_split_gap_pt": CLUSTER_SPLIT_GAP_PT,
            "profile": "docs/TABLE_HIERARCHY_BIN_CALIBRATION.md",
            "prexc_profile": "docs/prexc_code.md",
        },
        "roots": ["root"],
        "nodes": nodes,
        "tier_fits": {str(page): builder.tier_fits[page] for page in pages},
        "column_roles": {str(page): builder.column_roles[page] for page in pages},
        "page_flags": {str(page): builder.page_flags.get(page, []) for page in pages},
        "diagnostics": {
            "n_nodes": len(nodes), "n_pages": len(pages),
            "kind_counts": kind_counts,
            "n_review_flags": sum(1 for page in pages for flag in builder.page_flags.get(page, [])
                                  if flag["severity"] == "review"),
            "n_info_flags": sum(1 for page in pages for flag in builder.page_flags.get(page, [])
                                if flag["severity"] == "info"),
            "prexc": prexc,
        },
    }
    stamp_meta(tree, stage="layer:by_ou_tree", producer="deterministic_by_ou_tree_v2")
    return tree


def _page_slice(page: int, tree: dict[str, Any]) -> dict[str, Any]:
    nodes_by_page = {node["id"]: node for node in tree["nodes"] if node.get("page") == page}
    payload = {
        "page": page,
        "table": {"table_id": tree["table"]["table_id"], "table_type": tree["table"]["table_type"]},
        "tier_fit": tree["tier_fits"].get(str(page)),
        "column_roles": tree["column_roles"].get(str(page)),
        "nodes": list(nodes_by_page.values()),
        "flags": tree["page_flags"].get(str(page), []),
        "diagnostics": {
            "n_nodes": len(nodes_by_page),
            "n_flags": len(tree["page_flags"].get(str(page), [])),
            "n_review_flags": sum(1 for flag in tree["page_flags"].get(str(page), [])
                                  if flag["severity"] == "review"),
        },
    }
    stamp_meta(payload, stage="layer:by_ou_tree", producer="deterministic_by_ou_tree_v2")
    return payload


def run_stage(context, *, seeds_path: Path = DEFAULT_SEEDS,
              layouts_path: Path = DEFAULT_LAYOUTS) -> dict[str, Any]:
    started_at, started = iso_now(), time.perf_counter()
    seeds = read_json(resolve_project_path(seeds_path))
    read_json(resolve_project_path(layouts_path))
    by_ou_tables = [table for table in seeds.get("tables") or []
                    if table.get("table_type") == "by_ou"]
    if not by_ou_tables:
        raise SystemExit("no by_ou table seed found")
    table_seed = by_ou_tables[0]
    span_start = int(table_seed["start"]["page"])
    span_end = int(table_seed["end"]["page"])
    pages = [page for page in context.pages if span_start <= page <= span_end]
    offspan = [page for page in context.pages if page not in pages]

    page_results: list[dict[str, Any]] = []
    page_inputs: list[dict[str, Any]] = []
    n_fail = 0
    for page in pages:
        page_started_at, page_started = iso_now(), time.perf_counter()
        try:
            geometry = read_json(
                context.store.layer_path("token_geometry_repair", page))
            structure = read_json(context.store.layer_path("table_structure", page))
            if structure.get("table_layout", {}).get("table_type") != "by_ou":
                result = {"page": page, "pass": False, "error_type": "TableTypeMismatch",
                          "error": f"table_type={structure.get('table_layout', {}).get('table_type')}"}
                n_fail += 1
            else:
                page_inputs.append({"page": page, "geometry": geometry, "structure": structure})
                result = {"page": page, "pass": True,
                          "n_rows": len(structure.get("row_sections") or [])}
        except Exception as error:
            result = {"page": page, "pass": False,
                      "error_type": type(error).__name__, "error": str(error)}
            n_fail += 1
        result.update({"started_at": page_started_at, "completed_at": iso_now(),
                       "timestamp_source": "captured",
                       "elapsed_s": round(time.perf_counter() - page_started, 3)})
        page_results.append(result)

    tree = assemble_tree(page_inputs, table_seed=table_seed) if page_inputs else None
    stage_root = context.store.stage_root("by_ou_tree")
    node_count_by_page = {str(entry["page"]): 0 for entry in page_inputs}
    if tree is not None:
        write_json_atomic(stage_root / "tree.json", tree)
        selected_pages = {entry["page"] for entry in page_inputs}
        for stale_path in (stage_root / "pages").glob("page-*.json"):
            try:
                stale_page = int(stale_path.stem.removeprefix("page-"))
            except ValueError:
                continue
            if stale_page not in selected_pages:
                stale_path.unlink()
        for entry in page_inputs:
            page = entry["page"]
            slice_payload = _page_slice(page, tree)
            node_count_by_page[str(page)] = slice_payload["diagnostics"]["n_nodes"]
            write_json_atomic(stage_root / "pages" / f"page-{page:04d}.json", slice_payload)

    flags_by_page = tree["page_flags"] if tree else {}
    for result in page_results:
        page = str(result["page"])
        result["n_nodes"] = node_count_by_page.get(page, 0)
        result["n_flags"] = len(flags_by_page.get(page, []))
        result["n_review_flags"] = sum(1 for flag in flags_by_page.get(page, [])
                                       if flag["severity"] == "review")

    summary = {
        "artifact_version": 1, "gate": "BY_OU_TABLE_TREE",
        "name": "deterministic_by_ou_tree", "scope": "by_ou_viewer_tree_v1",
        "n_pages": len(page_results), "n_fail": n_fail,
        "n_offspan_pages_skipped": len(offspan),
        "offspan_pages": offspan,
        "n_nodes": (tree or {}).get("diagnostics", {}).get("n_nodes", 0),
        "n_flags": sum(result.get("n_flags", 0) for result in page_results),
        "n_review_flags": sum(result.get("n_review_flags", 0) for result in page_results),
        "kind_counts": (tree or {}).get("diagnostics", {}).get("kind_counts", {}),
        "started_at": started_at, "completed_at": iso_now(),
        "timestamp_source": "captured",
        "elapsed_s": round(time.perf_counter() - started, 3),
        "pages": page_results, "pass": n_fail == 0,
    }
    write_json_atomic(context.store.stage_qa_path("by_ou_tree"), summary)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    add_stage_arguments(parser)
    summary = run_stage(make_context(parser.parse_args()))
    print(f"002.30 By-OU tree: pages={summary['n_pages']} nodes={summary['n_nodes']} "
          f"review_flags={summary['n_review_flags']} elapsed={summary['elapsed_s']}s")
    require_pass(summary)


if __name__ == "__main__":
    main()
