#!/usr/bin/env python3
"""Stage 002.40: deterministic PAP hierarchy tree for table exploration.

Inputs: 002.20-table-structure/pages/*.json, 002.10-token-geometry/pages/*.json,
and fixtures/pap_table_seeds.json
Outputs: 002.40-pap-tree/tree.json, pages/*.json, and qa/summary.json

The stage assigns PAP rows to the eight calibrated anchor-distance levels,
builds parents in document order, carries the active stack across contiguous
pages, and retains funding rows as excluded metadata children. Expense classes
and their sections share the far-left visual level, so their semantic nesting
is handled explicitly instead of widening or inventing a distance bin.
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
from _shared.timestamps import iso_now

DEFAULT_SEEDS = Path("fixtures/pap_table_seeds.json")

EXPENSE_CLASSES = {
    "MAINTENANCE AND OTHER OPERATING EXPENSES",
    "CAPITAL OUTLAYS",
}
TOP_SECTIONS = {
    "GENERAL ADMINISTRATIVE AND SUPPORT",
    "SUPPORT TO OPERATIONS",
    "OPERATIONS",
}
FUNDING_TEXT = re.compile(r"^(?:GOP|Loan Proceeds|GOP Loan Proceeds)$", re.IGNORECASE)
REGION_TEXT = re.compile(
    r"\bRegion(?:\s+[IVX]+(?:-[A-Z])?)?\b|National Capital Region|"
    r"Administrative Region|Nationwide|BARMM", re.IGNORECASE)
OFFICE_TEXT = re.compile(
    r"\b(?:Central|Regional|District Engineering|Bureau Proper)\s+Office\b|"
    r"\bDistrict Engineering Office\b|^Central Office$|^Bureau Proper$",
    re.IGNORECASE)
OUTCOME_TEXT = re.compile(r"ORGANIZATIONAL OUTCOME", re.IGNORECASE)
PROGRAM_TEXT = re.compile(r"\bPROGRAM\b", re.IGNORECASE)
MARKER_TEXT = re.compile(r"^(?:[A-Za-z]|\d+)[.)]$")
LEADING_MARKER = re.compile(r"^((?:[A-Za-z]|\d+)[.)])\s+")
LOCAL_CLUSTER_GAP_PT = 6.0
TYPICAL_LEVEL_STEP_PT = 18.0

FLAG_MESSAGES = {
    "outside_center_tolerance": "Row distance exceeds the fitted center tolerance.",
    "parent_carry_missing": "Requested pages begin without the reviewed PAP start context.",
    "carry_gap_reset": "Parent carry was reset because the requested pages are not contiguous.",
    "funding_metadata_excluded": "Funding metadata is retained but excluded from hierarchy inference.",
    "merged_funding_label": "GOP and Loan Proceeds were merged into one retained funding row.",
    "formatting_displacement": "A page-local hierarchy center is displaced from the calibrated profile.",
    "end_of_span_open_stack": "The reviewed PAP span ends with hierarchy parents still open.",
    "unclassified_distance": "Row distance could not be assigned to a calibrated PAP level.",
    "multiple_money_candidates_in_cell": "Inherited from stage 002.20: ambiguous amount cell.",
    "no_recurring_amount_column": "Inherited from stage 002.20: no recurring amount column.",
}
INFO_FLAGS = {"funding_metadata_excluded", "end_of_span_open_stack"}


def _clean_text(text: str) -> str:
    return " ".join(str(text or "").split())


def _amount_value(text: str) -> int | None:
    digits = re.sub(r"\D", "", _clean_text(text))
    return int(digits) if digits else None


def _nearest_rank(distance: float | None, centers: list[float]) -> int | None:
    if distance is None:
        return None
    return min(range(len(centers)), key=lambda rank: abs(float(distance) - centers[rank]))


def _page_centers(
    views: list[dict[str, Any]], global_centers: list[float]
) -> tuple[dict[int, float], dict[int, int], list[dict[str, Any]]]:
    """Cluster page distances, then number levels upward from the bottom anchor.

    PAP occasionally compresses or shifts its far-left levels (notably page
    688). Local gaps still separate them clearly. Anchoring the lowest cluster
    to the calibrated profile and walking upward also preserves intentional
    skipped levels such as the common 448 -> 409 jump.
    """
    distances = sorted(
        (float(view["distance"]) for view in views
         if not view["funding"] and view["distance"] is not None),
        reverse=True)
    if not distances:
        return {}, {}, []
    groups: list[list[float]] = [[distances[0]]]
    for distance in distances[1:]:
        if groups[-1][-1] - distance > LOCAL_CLUSTER_GAP_PT:
            groups.append([distance])
        else:
            groups[-1].append(distance)
    centers = [float(statistics.median(values)) for values in groups]
    ranks = [0] * len(centers)
    ranks[-1] = int(_nearest_rank(centers[-1], global_centers) or 0)
    for index in range(len(centers) - 2, -1, -1):
        gap = centers[index] - centers[index + 1]
        step = max(1, round(gap / TYPICAL_LEVEL_STEP_PT))
        ranks[index] = max(0, ranks[index + 1] - step)
    clusters = [
        {"rank": rank, "center": center, "support": len(values)}
        for rank, center, values in zip(ranks, centers, groups)
    ]
    fitted = {item["rank"]: item["center"] for item in clusters}
    support = {item["rank"]: item["support"] for item in clusters}
    return fitted, support, clusters


def _page_rank(distance: float | None, clusters: list[dict[str, Any]],
               global_centers: list[float]) -> int | None:
    if distance is None:
        return None
    if not clusters:
        return _nearest_rank(distance, global_centers)
    return int(min(clusters, key=lambda item: abs(float(distance) - item["center"]))["rank"])


def _row_view(row: dict[str, Any], structure: dict[str, Any],
              phrases: dict[int, dict[str, Any]]) -> dict[str, Any] | None:
    row_id = int(row["row_section_id"])
    cells = [cell for cell in structure.get("cell_sections") or []
             if int(cell["row_section_id"]) == row_id]
    label_cell = next((cell for cell in cells if cell["column_role"] == "Labels"), None)
    label = _clean_text((label_cell or {}).get("text") or "")
    amounts: dict[str, dict[str, Any]] = {}
    total: dict[str, Any] | None = None
    for cell in sorted((cell for cell in cells if cell["column_role"] != "Labels"),
                       key=lambda item: int(item["column_section_id"])):
        text = _clean_text(cell.get("text") or "")
        if not text:
            continue
        phrase_ids = [int(value) for value in cell.get("phrase_ids") or []]
        entry = {
            "role": cell["column_role"],
            "text": text,
            "value": _amount_value(text) if len(phrase_ids) <= 1 else None,
            "phrase_ids": phrase_ids,
        }
        amounts[cell["column_role"]] = entry
        total = entry
    phrase_ids = [int(value) for value in row.get("phrase_ids") or []]
    if not label and not amounts:
        return None
    left_ids = [int(value) for value in row.get("left_of_label_phrase_ids") or []]
    prefixes = [_clean_text((phrases.get(value) or {}).get("text") or "")
                for value in left_ids]
    prefixes = [value for value in prefixes if value]
    marker = next((value for value in prefixes if MARKER_TEXT.match(value)), None)
    if marker is None and (leading := LEADING_MARKER.match(label)):
        marker = leading.group(1)
    boundary = row.get("label_left_boundary") or {}
    return {
        "row_section_id": row_id,
        "label": label,
        "distance": boundary.get("anchor_distance"),
        "marker": marker,
        "prefix_text": " ".join(prefixes) or None,
        "funding": bool(FUNDING_TEXT.match(label)),
        "amounts": amounts,
        "total": total,
        "phrase_ids": phrase_ids,
        "label_phrase_ids": [int(value) for value in (label_cell or {}).get("phrase_ids") or []],
        "token_ids": sorted({int(token) for phrase_id in phrase_ids
                             for token in (phrases.get(phrase_id) or {}).get("token_ids") or []}),
        "bbox": row.get("bbox"),
    }


def _kind(label: str, rank: int, *, expense: bool, top_section: bool) -> str:
    if expense:
        return "expense_class"
    if top_section:
        return "section"
    if OUTCOME_TEXT.search(label):
        return "outcome"
    if REGION_TEXT.search(label):
        return "region"
    if OFFICE_TEXT.search(label):
        return "office"
    if PROGRAM_TEXT.search(label) and rank <= 3:
        return "program"
    if rank >= 7:
        return "project"
    if rank >= 5:
        return "intermediate"
    return "group"


class PapTreeBuilder:
    def __init__(self, seed: dict[str, Any]):
        self.seed = seed
        self.global_centers = [float(value) for value in seed["distance_centers_pt"]]
        self.tolerance = float(seed.get("matching_tolerance_pt") or 4.0)
        self.nodes: dict[str, dict[str, Any]] = {}
        self.order: list[str] = []
        self.stack: list[dict[str, Any]] = []
        self.flags: dict[int, list[dict[str, Any]]] = {}
        self.fits: dict[int, dict[str, Any]] = {}
        self.columns: dict[int, list[dict[str, Any]]] = {}
        self.emit({
            "id": "root", "parent": None, "kind": "table_root", "tier": -1,
            "geometric_rank": None, "label": "Programs / Activities / Projects (PAP)",
            "page": None, "row_section_id": None, "amounts": {}, "total": None,
            "flags": [],
        })
        self.stack = [{"rank": -99, "id": "root", "same_level_child": False}]

    def flag(self, page: int, code: str, **details: Any) -> None:
        entry = {
            "code": code,
            "severity": "info" if code in INFO_FLAGS else "review",
            "message": FLAG_MESSAGES.get(code, code),
        }
        entry.update({key: value for key, value in details.items()
                      if value is not None and key not in {"code", "message", "severity"}})
        self.flags.setdefault(page, []).append(entry)

    def emit(self, node: dict[str, Any]) -> str:
        node["children"] = []
        self.nodes[node["id"]] = node
        self.order.append(node["id"])
        parent = node.get("parent")
        if parent in self.nodes:
            self.nodes[parent]["children"].append(node["id"])
        return node["id"]

    def _normal_parent(self, rank: int) -> str:
        while self.stack and int(self.stack[-1]["rank"]) >= rank:
            self.stack.pop()
        return str(self.stack[-1]["id"]) if self.stack else "root"

    def _same_level_parent(self, rank: int) -> str:
        while self.stack and int(self.stack[-1]["rank"]) > rank:
            self.stack.pop()
        while (self.stack and int(self.stack[-1]["rank"]) == rank
               and self.stack[-1]["same_level_child"]):
            self.stack.pop()
        return str(self.stack[-1]["id"]) if self.stack else "root"

    def build_page(self, page: int, geometry: dict[str, Any], structure: dict[str, Any],
                   previous_page: int | None) -> None:
        if previous_page is None and page != int(self.seed["start"]["page"]):
            self.flag(page, "parent_carry_missing")
        elif previous_page is not None and page != previous_page + 1:
            self.stack = [{"rank": -99, "id": "root", "same_level_child": False}]
            self.flag(page, "carry_gap_reset", from_page=previous_page)

        phrases = {int(item["phrase_id"]): item for item in geometry.get("phrases") or []}
        views = [view for row in structure.get("row_sections") or []
                 if (view := _row_view(row, structure, phrases)) is not None]
        fitted, support, clusters = _page_centers(views, self.global_centers)
        self.fits[page] = {
            "global_centers_pt": self.global_centers,
            "fitted_centers_pt": {str(rank): round(center, 3)
                                  for rank, center in fitted.items()},
            "support": {str(rank): count for rank, count in support.items()},
            "clusters": [{**item, "center": round(item["center"], 3)}
                         for item in clusters],
            "tolerance_pt": self.tolerance,
        }
        for cluster in clusters:
            nearest_profile = min(
                self.global_centers,
                key=lambda center: abs(cluster["center"] - center))
            displacement = abs(cluster["center"] - nearest_profile)
            if displacement > self.tolerance:
                self.flag(
                    page, "formatting_displacement",
                    geometric_rank=cluster["rank"],
                    center=round(cluster["center"], 3),
                    nearest_profile_center=nearest_profile,
                    displacement=round(displacement, 3),
                    support=cluster["support"])
        self.columns[page] = [
            {"role": item["role"], "column_section_id": int(item["column_section_id"])}
            for item in structure.get("column_sections") or []]
        findings_by_row: dict[int, list[dict[str, Any]]] = {}
        for finding in structure.get("findings") or []:
            if finding.get("row_section_id") is not None:
                findings_by_row.setdefault(int(finding["row_section_id"]), []).append(finding)
            elif finding.get("code") == "no_recurring_amount_column":
                self.flag(page, "no_recurring_amount_column")

        for view in views:
            self.build_row(page, view, fitted, clusters,
                           findings_by_row.get(view["row_section_id"]) or [])

    def build_row(self, page: int, view: dict[str, Any], fitted: dict[int, float],
                  clusters: list[dict[str, Any]],
                  findings: list[dict[str, Any]]) -> None:
        node_id = f"p{page}:r{view['row_section_id']}"
        node_flags: list[str] = []
        for finding in findings:
            code = str(finding.get("code") or "")
            if code in FLAG_MESSAGES:
                node_flags.append(code)
                self.flag(page, code, row_section_id=view["row_section_id"],
                          phrase_ids=finding.get("phrase_ids"))

        if view["funding"]:
            merged_funding = (
                "gop" in view["label"].lower()
                and "loan proceeds" in view["label"].lower())
            if merged_funding:
                node_flags.append("merged_funding_label")
            node = self._node(node_id, page, view, kind="funding", rank=None,
                              center=None, delta=None, confidence="semantic",
                              flags=node_flags + ["funding_metadata_excluded"])
            node["parent"] = str(self.stack[-1]["id"])
            node["excluded"] = True
            self.emit(node)
            self.flag(page, "funding_metadata_excluded",
                      row_section_id=view["row_section_id"])
            if merged_funding:
                self.flag(page, "merged_funding_label",
                          row_section_id=view["row_section_id"])
            return

        rank = _page_rank(view["distance"], clusters, self.global_centers)
        if rank is None:
            node = self._node(node_id, page, view, kind="unclassified", rank=None,
                              center=None, delta=None, confidence="review",
                              flags=node_flags + ["unclassified_distance"])
            node["parent"] = str(self.stack[-1]["id"])
            self.emit(node)
            self.flag(page, "unclassified_distance",
                      row_section_id=view["row_section_id"])
            return

        center = fitted.get(rank, self.global_centers[rank])
        delta = abs(float(view["distance"]) - center)
        confidence = "high" if delta <= 1.5 else "medium"
        if delta > self.tolerance:
            confidence = "review"
            node_flags.append("outside_center_tolerance")
            self.flag(page, "outside_center_tolerance",
                      row_section_id=view["row_section_id"],
                      distance=view["distance"], center=round(center, 3))

        upper = view["label"].upper()
        expense = upper in EXPENSE_CLASSES
        top_section = upper in TOP_SECTIONS
        same_level_child = rank == 0 and bool(view["marker"]) and not expense
        if expense:
            parent = "root"
            self.stack = [{"rank": -99, "id": "root", "same_level_child": False}]
            stack_rank = -1
        elif top_section:
            while self.stack and int(self.stack[-1]["rank"]) >= 0:
                self.stack.pop()
            parent = str(self.stack[-1]["id"]) if self.stack else "root"
            stack_rank = 0
        elif same_level_child:
            parent = self._same_level_parent(rank)
            stack_rank = rank
        else:
            parent = self._normal_parent(rank)
            stack_rank = rank

        node = self._node(
            node_id, page, view,
            kind=_kind(view["label"], rank, expense=expense, top_section=top_section),
            rank=rank, center=center, delta=delta, confidence=confidence,
            flags=node_flags)
        node["parent"] = parent
        self.emit(node)
        self.stack.append({
            "rank": stack_rank,
            "id": node_id,
            "same_level_child": same_level_child,
        })

    @staticmethod
    def _node(node_id: str, page: int, view: dict[str, Any], *, kind: str,
              rank: int | None, center: float | None, delta: float | None,
              confidence: str, flags: list[str]) -> dict[str, Any]:
        return {
            "id": node_id, "parent": None, "kind": kind, "tier": rank,
            "geometric_rank": rank, "label": view["label"],
            "marker": view["marker"], "prefix_text": view["prefix_text"],
            "page": page, "row_section_id": view["row_section_id"],
            "phrase_ids": view["phrase_ids"],
            "label_phrase_ids": view["label_phrase_ids"],
            "token_ids": view["token_ids"], "bbox": view["bbox"],
            "distance": view["distance"],
            "center": None if center is None else round(center, 3),
            "delta": None if delta is None else round(delta, 3),
            "confidence": confidence, "amounts": view["amounts"],
            "total": view["total"], "flags": flags,
        }


def assemble_tree(page_inputs: list[dict[str, Any]], *, table_seed: dict[str, Any]) -> dict[str, Any]:
    builder = PapTreeBuilder(table_seed)
    previous_page: int | None = None
    for entry in page_inputs:
        builder.build_page(entry["page"], entry["geometry"], entry["structure"],
                           previous_page)
        previous_page = entry["page"]
    pages = [entry["page"] for entry in page_inputs]
    if (pages and pages[-1] == int(table_seed["end"]["page"])
            and len(builder.stack) > 1):
        builder.flag(
            pages[-1], "end_of_span_open_stack",
            open_node_ids=[entry["id"] for entry in builder.stack[1:]])
    nodes = [builder.nodes[node_id] for node_id in builder.order]
    kind_counts: dict[str, int] = {}
    for item in nodes:
        kind_counts[item["kind"]] = kind_counts.get(item["kind"], 0) + 1
    payload = {
        "algorithm": {"name": "deterministic_pap_tree", "version": 1},
        "table": {
            "table_id": table_seed["table_id"], "table_type": "pap",
            "title": "Programs / Activities / Projects (PAP)",
            "reviewed_span": {
                "start_page": table_seed["start"]["page"],
                "end_page": table_seed["end"]["page"],
            },
            "requested_pages": pages,
            "carry_policy": table_seed.get("carry_policy") or {},
        },
        "calibration": {
            "global_centers_pt": builder.global_centers,
            "funding_metadata_centers_pt": table_seed.get("funding_metadata_centers_pt"),
            "center_tolerance_pt": builder.tolerance,
            "profile": "docs/TABLE_HIERARCHY_BIN_CALIBRATION.md",
        },
        "roots": ["root"],
        "nodes": nodes,
        "tier_fits": {str(page): builder.fits[page] for page in pages},
        "column_roles": {str(page): builder.columns[page] for page in pages},
        "page_flags": {str(page): builder.flags.get(page, []) for page in pages},
        "diagnostics": {
            "n_nodes": len(nodes), "n_pages": len(pages),
            "kind_counts": kind_counts,
            "n_review_flags": sum(
                flag["severity"] == "review" for flags in builder.flags.values()
                for flag in flags),
            "n_info_flags": sum(
                flag["severity"] == "info" for flags in builder.flags.values()
                for flag in flags),
        },
    }
    stamp_meta(payload, stage="layer:pap_tree",
               producer="deterministic_pap_tree_v1")
    return payload


def _page_slice(page: int, tree: dict[str, Any]) -> dict[str, Any]:
    nodes = [node for node in tree["nodes"] if node.get("page") == page]
    flags = tree["page_flags"].get(str(page), [])
    payload = {
        "page": page,
        "table": {"table_id": tree["table"]["table_id"], "table_type": "pap"},
        "tier_fit": tree["tier_fits"].get(str(page)),
        "column_roles": tree["column_roles"].get(str(page)),
        "nodes": nodes, "flags": flags,
        "diagnostics": {
            "n_nodes": len(nodes), "n_flags": len(flags),
            "n_review_flags": sum(flag["severity"] == "review" for flag in flags),
        },
    }
    stamp_meta(payload, stage="layer:pap_tree",
               producer="deterministic_pap_tree_v1")
    return payload


def run_stage(context, *, seeds_path: Path = DEFAULT_SEEDS) -> dict[str, Any]:
    started_at, started = iso_now(), time.perf_counter()
    seeds = read_json(resolve_project_path(seeds_path))
    seed = next((item for item in seeds.get("tables") or []
                 if item.get("table_type") == "pap"), None)
    if seed is None:
        raise SystemExit("no PAP table seed found")
    start_page, end_page = int(seed["start"]["page"]), int(seed["end"]["page"])
    pages = [page for page in context.pages if start_page <= page <= end_page]
    offspan = [page for page in context.pages if page not in pages]
    inputs: list[dict[str, Any]] = []
    results: list[dict[str, Any]] = []
    n_fail = 0
    for page in pages:
        page_started_at, page_started = iso_now(), time.perf_counter()
        try:
            geometry = read_json(
                context.store.layer_path("token_geometry_repair", page))
            structure = read_json(context.store.layer_path("table_structure", page))
            if structure.get("table_layout", {}).get("table_type") != "pap":
                raise ValueError(
                    f"expected PAP structure, got "
                    f"{structure.get('table_layout', {}).get('table_type')}")
            inputs.append({"page": page, "geometry": geometry,
                           "structure": structure})
            result = {"page": page, "pass": True,
                      "n_rows": len(structure.get("row_sections") or [])}
        except Exception as error:
            n_fail += 1
            result = {"page": page, "pass": False,
                      "error_type": type(error).__name__, "error": str(error)}
        result.update({
            "started_at": page_started_at, "completed_at": iso_now(),
            "timestamp_source": "captured",
            "elapsed_s": round(time.perf_counter() - page_started, 3),
        })
        results.append(result)

    tree = assemble_tree(inputs, table_seed=seed) if inputs else None
    stage_root = context.store.stage_root("pap_tree")
    counts: dict[int, dict[str, int]] = {}
    if tree is not None:
        write_json_atomic(stage_root / "tree.json", tree)
        selected = {entry["page"] for entry in inputs}
        for stale in (stage_root / "pages").glob("page-*.json"):
            try:
                stale_page = int(stale.stem.removeprefix("page-"))
            except ValueError:
                continue
            if stale_page not in selected:
                stale.unlink()
        for entry in inputs:
            page = entry["page"]
            page_payload = _page_slice(page, tree)
            counts[page] = page_payload["diagnostics"]
            write_json_atomic(
                stage_root / "pages" / f"page-{page:04d}.json",
                page_payload)
    for result in results:
        result.update(counts.get(result["page"], {
            "n_nodes": 0, "n_flags": 0, "n_review_flags": 0}))

    summary = {
        "artifact_version": 1, "gate": "PAP_TABLE_TREE",
        "name": "deterministic_pap_tree", "scope": "pap_viewer_tree_v1",
        "n_pages": len(results), "n_fail": n_fail,
        "n_offspan_pages_skipped": len(offspan), "offspan_pages": offspan,
        "n_nodes": (tree or {}).get("diagnostics", {}).get("n_nodes", 0),
        "n_flags": sum(result["n_flags"] for result in results),
        "n_review_flags": sum(result["n_review_flags"] for result in results),
        "kind_counts": (tree or {}).get("diagnostics", {}).get("kind_counts", {}),
        "started_at": started_at, "completed_at": iso_now(),
        "timestamp_source": "captured",
        "elapsed_s": round(time.perf_counter() - started, 3),
        "pages": results, "pass": n_fail == 0,
    }
    write_json_atomic(context.store.stage_qa_path("pap_tree"), summary)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    add_stage_arguments(parser)
    summary = run_stage(make_context(parser.parse_args()))
    print(f"002.40 PAP tree: pages={summary['n_pages']} "
          f"nodes={summary['n_nodes']} review_flags={summary['n_review_flags']} "
          f"elapsed={summary['elapsed_s']}s")
    require_pass(summary)


if __name__ == "__main__":
    main()
