#!/usr/bin/env python3
"""Stage 002.50: validate each tree parent total against immediate children.

Inputs: 002.30-by-ou-tree/tree.json and 002.40-pap-tree/tree.json
Outputs: 002.50-tree-totals/validation.json, pages/*.json, and qa/summary.json

Non-additive children (excluded from the child sum):
- explicit `subtotal` / `grand_total` rows (would double-count detail siblings)
- `funding` metadata (Loan/GOP breakdowns already inside the office/parent total)
- PREXC LFP/FAP project codes (identifier digit 2/3): program lines total the
  regular activity stream only; project siblings are separate appropriations

Checks touching the last page of a partial tree artifact are reported as
boundary-incomplete rather than as false mismatches.
"""
from __future__ import annotations

import argparse
import re
import time
from pathlib import Path
from typing import Any

from _common import add_stage_arguments, make_context, require_pass
from _shared.artifacts import read_json, write_json_atomic
from _shared.contracts import stamp_meta
from _shared.prexc import is_project_code
from _shared.timestamps import iso_now

TREE_SOURCES = (
    ("by_ou", "002.30-by-ou-tree"),
    ("pap", "002.40-pap-tree"),
)
NON_ADDITIVE_KINDS = {"subtotal", "grand_total", "funding"}
REVIEW_STATUSES = {"mismatch", "missing_parent_total", "incomplete_children"}


def _amount_value(node: dict[str, Any]) -> int | None:
    total = node.get("total") or {}
    value = total.get("value")
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    digits = re.sub(r"\D", "", str(total.get("text") or ""))
    return int(digits) if digits else None


def _is_non_additive_child(node: dict[str, Any]) -> tuple[bool, str | None]:
    kind = str(node.get("kind") or "")
    if kind in NON_ADDITIVE_KINDS:
        return True, "semantic_aggregate" if kind in {"subtotal", "grand_total"} else "funding_metadata"
    if is_project_code(str(node.get("code") or "")):
        return True, "prexc_project_sibling"
    return False, None


def _descendant_max_pages(nodes: dict[str, dict[str, Any]]) -> dict[str, int | None]:
    memo: dict[str, int | None] = {}
    visiting: set[str] = set()

    def visit(node_id: str) -> int | None:
        if node_id in memo:
            return memo[node_id]
        if node_id in visiting:
            return None
        visiting.add(node_id)
        node = nodes[node_id]
        pages = [int(node["page"])] if node.get("page") is not None else []
        for child_id in node.get("children") or []:
            if child_id in nodes:
                child_page = visit(child_id)
                if child_page is not None:
                    pages.append(child_page)
        visiting.remove(node_id)
        memo[node_id] = max(pages) if pages else None
        return memo[node_id]

    for node_id in nodes:
        visit(node_id)
    return memo


def _is_transparent_shell(node: dict[str, Any]) -> bool:
    """Synthesized PREXC shells have no amounts; roll up through them."""
    return bool(node.get("synthetic")) or str(node.get("kind") or "").startswith("prexc_")


def _expand_additive_children(
    children: list[dict[str, Any]], nodes: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Flatten transparent shells; collect excluded non-additive rows."""
    included: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []

    def visit(child: dict[str, Any]) -> None:
        if _is_transparent_shell(child):
            for grandchild_id in child.get("children") or []:
                grandchild = nodes.get(str(grandchild_id))
                if grandchild is not None:
                    visit(grandchild)
            return
        skip, reason = _is_non_additive_child(child)
        if skip:
            excluded.append({
                "id": child["id"], "label": child.get("label"),
                "kind": child.get("kind"), "code": child.get("code"),
                "reason": reason,
            })
            return
        included.append(child)

    for child in children:
        visit(child)
    return included, excluded


def validate_tree(
    tree: dict[str, Any], *, selected_pages: set[int],
    absolute_tolerance: int = 0
) -> dict[str, Any]:
    nodes = {str(node["id"]): node for node in tree.get("nodes") or []}
    descendant_max = _descendant_max_pages(nodes)
    requested_pages = [int(page) for page in tree.get("table", {}).get("requested_pages") or []]
    artifact_last = max(requested_pages) if requested_pages else None
    reviewed_end = tree.get("table", {}).get("reviewed_span", {}).get("end_page")
    partial_artifact = (
        artifact_last is not None and reviewed_end is not None
        and artifact_last < int(reviewed_end))
    checks: list[dict[str, Any]] = []

    for parent in tree.get("nodes") or []:
        if _is_transparent_shell(parent):
            continue
        page = parent.get("page")
        child_ids = [str(value) for value in parent.get("children") or []]
        if page is None or int(page) not in selected_pages or not child_ids:
            continue
        children = [nodes[child_id] for child_id in child_ids if child_id in nodes]
        included, excluded = _expand_additive_children(children, nodes)
        parent_amount = _amount_value(parent)
        child_rows = [
            {
                "id": child["id"], "page": child.get("page"),
                "label": child.get("label"), "kind": child.get("kind"),
                "excluded": bool(child.get("excluded")),
                "amount": _amount_value(child),
                "amount_text": (child.get("total") or {}).get("text"),
            }
            for child in included
        ]
        known_amounts = [
            child["amount"] for child in child_rows
            if child["amount"] is not None]
        missing_ids = [
            child["id"] for child in child_rows
            if child["amount"] is None]
        child_sum = sum(known_amounts) if known_amounts else None
        difference = (
            parent_amount - child_sum
            if parent_amount is not None and child_sum is not None else None)
        boundary_incomplete = bool(
            partial_artifact and artifact_last is not None
            and descendant_max.get(str(parent["id"])) == artifact_last)

        if not included:
            status = "no_additive_children"
        elif parent_amount is None:
            status = "missing_parent_total"
        elif missing_ids:
            status = "incomplete_children"
        elif (boundary_incomplete and difference is not None
              and difference < -absolute_tolerance):
            # Future non-negative children can only increase an existing
            # overcount, so this mismatch is definitive even at a partial edge.
            status = "mismatch"
        elif boundary_incomplete:
            status = "boundary_incomplete"
        elif abs(int(difference or 0)) <= absolute_tolerance:
            status = "pass"
        else:
            status = "mismatch"

        checks.append({
            "check_id": f"{tree.get('table', {}).get('table_id', 'tree')}:{parent['id']}",
            "table_id": tree.get("table", {}).get("table_id"),
            "table_type": tree.get("table", {}).get("table_type"),
            "parent_id": parent["id"], "parent_page": int(page),
            "parent_label": parent.get("label"), "parent_kind": parent.get("kind"),
            "parent_amount": parent_amount,
            "parent_amount_text": (parent.get("total") or {}).get("text"),
            "child_sum": child_sum, "difference": difference,
            "absolute_difference": abs(difference) if difference is not None else None,
            "absolute_tolerance": absolute_tolerance,
            "status": status,
            "n_children": len(children), "n_additive_children": len(included),
            "n_excluded_children": len(excluded),
            "missing_child_amount_ids": missing_ids,
            "boundary_incomplete": boundary_incomplete,
            "children": child_rows, "excluded_children": excluded,
        })

    status_counts: dict[str, int] = {}
    for check in checks:
        status = check["status"]
        status_counts[status] = status_counts.get(status, 0) + 1
    return {
        "table": tree.get("table") or {},
        "source_algorithm": tree.get("algorithm") or {},
        "checks": checks,
        "diagnostics": {
            "n_checks": len(checks),
            "n_comparable": status_counts.get("pass", 0) + status_counts.get("mismatch", 0),
            "n_pass": status_counts.get("pass", 0),
            "n_mismatch": status_counts.get("mismatch", 0),
            "n_review": sum(status_counts.get(status, 0) for status in REVIEW_STATUSES),
            "status_counts": status_counts,
            "partial_artifact": partial_artifact,
        },
    }


def _page_slice(page: int, table_results: list[dict[str, Any]]) -> dict[str, Any]:
    checks = [
        check for result in table_results for check in result["checks"]
        if check["parent_page"] == page]
    status_counts: dict[str, int] = {}
    for check in checks:
        status_counts[check["status"]] = status_counts.get(check["status"], 0) + 1
    payload = {
        "page": page, "checks": checks,
        "diagnostics": {
            "n_checks": len(checks),
            "n_comparable": status_counts.get("pass", 0) + status_counts.get("mismatch", 0),
            "n_pass": status_counts.get("pass", 0),
            "n_mismatch": status_counts.get("mismatch", 0),
            "n_review": sum(status_counts.get(status, 0) for status in REVIEW_STATUSES),
            "status_counts": status_counts,
        },
    }
    stamp_meta(payload, stage="layer:tree_totals",
               producer="immediate_child_totals_v1")
    return payload


def run_stage(context, *, absolute_tolerance: int = 0) -> dict[str, Any]:
    started_at, started = iso_now(), time.perf_counter()
    table_results: list[dict[str, Any]] = []
    sources: list[dict[str, Any]] = []
    n_fail = 0
    for table_type, directory in TREE_SOURCES:
        path = context.run_dir / directory / "tree.json"
        if not path.is_file():
            sources.append({
                "table_type": table_type, "path": str(path.relative_to(context.run_dir)),
                "status": "missing",
            })
            continue
        try:
            result = validate_tree(
                read_json(path), selected_pages=set(context.pages),
                absolute_tolerance=absolute_tolerance)
            table_results.append(result)
            sources.append({
                "table_type": table_type, "path": str(path.relative_to(context.run_dir)),
                "status": "loaded", "n_checks": result["diagnostics"]["n_checks"],
            })
        except Exception as error:
            n_fail += 1
            sources.append({
                "table_type": table_type, "path": str(path.relative_to(context.run_dir)),
                "status": "failed", "error_type": type(error).__name__,
                "error": str(error),
            })

    payload = {
        "algorithm": {
            "name": "immediate_child_totals", "version": 2,
            "absolute_tolerance": absolute_tolerance,
            "non_additive_child_kinds": sorted(NON_ADDITIVE_KINDS),
            "funding_children_are_additive": False,
            "prexc_project_siblings_excluded": True,
            "prexc_shells_are_transparent": True,
        },
        "requested_pages": context.pages, "sources": sources,
        "tables": table_results,
    }
    totals = {
        "n_checks": sum(result["diagnostics"]["n_checks"] for result in table_results),
        "n_comparable": sum(result["diagnostics"]["n_comparable"] for result in table_results),
        "n_pass": sum(result["diagnostics"]["n_pass"] for result in table_results),
        "n_mismatch": sum(result["diagnostics"]["n_mismatch"] for result in table_results),
        "n_review": sum(result["diagnostics"]["n_review"] for result in table_results),
    }
    payload["diagnostics"] = totals
    stamp_meta(payload, stage="layer:tree_totals",
               producer="immediate_child_totals_v1")

    stage_root = context.store.stage_root("tree_totals")
    write_json_atomic(stage_root / "validation.json", payload)
    selected = set(context.pages)
    for stale in (stage_root / "pages").glob("page-*.json"):
        try:
            stale_page = int(stale.stem.removeprefix("page-"))
        except ValueError:
            continue
        if stale_page not in selected:
            stale.unlink()
    page_results: list[dict[str, Any]] = []
    for page in context.pages:
        page_payload = _page_slice(page, table_results)
        write_json_atomic(
            stage_root / "pages" / f"page-{page:04d}.json", page_payload)
        page_results.append({
            "page": page, "pass": True, **page_payload["diagnostics"]})

    summary = {
        "artifact_version": 1, "gate": "TREE_TOTALS",
        "name": "immediate_child_totals", "scope": "tree_parent_rollups_v1",
        "n_pages": len(context.pages), "n_fail": n_fail,
        **totals, "sources": sources,
        "started_at": started_at, "completed_at": iso_now(),
        "timestamp_source": "captured",
        "elapsed_s": round(time.perf_counter() - started, 3),
        "pages": page_results, "pass": n_fail == 0,
    }
    write_json_atomic(context.store.stage_qa_path("tree_totals"), summary)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    add_stage_arguments(parser)
    parser.add_argument(
        "--absolute-tolerance", type=int, default=0,
        help="Allowed absolute difference in whole currency units (default: 0).")
    args = parser.parse_args()
    summary = run_stage(
        make_context(args), absolute_tolerance=max(0, args.absolute_tolerance))
    print(
        f"002.50 tree totals: checks={summary['n_checks']} "
        f"pass={summary['n_pass']} mismatch={summary['n_mismatch']} "
        f"review={summary['n_review']} elapsed={summary['elapsed_s']}s")
    require_pass(summary)


if __name__ == "__main__":
    main()
