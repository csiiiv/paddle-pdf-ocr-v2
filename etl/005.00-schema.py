#!/usr/bin/env python3
"""Stage 005.00: canonical extract to page/zone schema decisions and QA.

Inputs: 004.00-extract/pages/*.json
Outputs: 005.00-schema/pages/*.json and qa/summary.json
"""

from __future__ import annotations

import argparse
from collections import defaultdict
import re
import statistics
import time
from typing import Any

from _common import add_stage_arguments, make_context, require_pass
from _shared.artifacts import read_json, write_json_atomic
from _shared.contracts import stamp_meta, validate_extract, validate_schema
from _shared.timestamps import iso_now


ROLE_PATTERNS = (
    ("PS", re.compile(r"\b(?:personnel(?:\s+services?)?|ps)\b", re.I)),
    ("MOOE", re.compile(r"\b(?:maintenance(?:\s+and\s+other\s+operating\s+expenses?)?|mooe)\b", re.I)),
    ("CO", re.compile(r"\b(?:capital\s+outlays?|co)\b", re.I)),
    ("Total", re.compile(r"\btotal\b", re.I)),
)
AMOUNT_HEADER = re.compile(r"\bamount\s*\(\s*php\s*\)", re.I)
YEAR_CUE = re.compile(r"\b(?:20\d{2}|actual|current|proposed|gaa\s+targets?|staffing)\b", re.I)
UNIT_CUE = re.compile(r"\b(?:in\s+)?thousand\s+pesos\b", re.I)
MONEY = re.compile(r"^(?:p(?:hp)?\s*)?\(?-?\d[\d,]*(?:\.\d+)?\)?$", re.I)


def is_money(text: str) -> bool:
    compact = " ".join(str(text).strip().split())
    if not MONEY.fullmatch(compact):
        return False
    digits = re.sub(r"\D", "", compact)
    return not (len(digits) == 4 and 1900 <= int(digits) <= 2100)


def table_evidence(table: dict[str, Any]) -> dict[str, Any]:
    cells = table.get("cells") or []
    header_limit = min((int(cell.get("row", 0)) for cell in cells if is_money(cell.get("text", ""))), default=4)
    header_cells = [cell for cell in cells if int(cell.get("row", 0)) <= header_limit]
    roles_by_col: dict[int, str] = {}
    for cell in header_cells:
        text = str(cell.get("text") or "")
        for role, pattern in ROLE_PATTERNS:
            if pattern.search(text):
                roles_by_col[int(cell.get("col", 0))] = role
                break
    money_by_col: dict[int, list[float]] = defaultdict(list)
    for cell in cells:
        if is_money(cell.get("text", "")) and cell.get("bbox"):
            bbox = cell["bbox"]
            money_by_col[int(cell.get("col", 0))].append((bbox[0] + bbox[2]) / 2)
    centers = {col: round(statistics.median(xs), 2) for col, xs in money_by_col.items()}
    blob = " ".join(str(cell.get("text") or "") for cell in header_cells)
    return {
        "roles_by_col": roles_by_col,
        "money_cols": sorted(money_by_col),
        "centers_by_col": centers,
        "n_money_hits": sum(len(xs) for xs in money_by_col.values()),
        "has_amount_header": bool(AMOUNT_HEADER.search(blob)),
        "has_year_cue": bool(YEAR_CUE.search(blob)),
        "has_unit_cue": bool(UNIT_CUE.search(blob)),
        "header_text": blob,
    }


def zone_text(zone: dict[str, Any], extract: dict[str, Any]) -> str:
    line_ids = set(zone.get("line_ids") or [])
    lines = extract.get("lines") or []
    selected = [line for line in lines if line.get("line_id") in line_ids] if line_ids else [
        line for line in lines if line.get("region_id") == zone.get("region_id") and not line.get("chrome")
    ]
    return " ".join(str(line.get("text") or "") for line in selected[:40])


def decision_status(confidence: float) -> str:
    if confidence >= 0.8:
        return "accept"
    if confidence >= 0.5:
        return "review"
    return "reject"


def infer_zone(
    zone: dict[str, Any], extract: dict[str, Any], *,
    table: dict[str, Any] | None, carry: dict[str, Any] | None,
) -> dict[str, Any]:
    evidence = table_evidence(table or {})
    text = f"{evidence['header_text']} {zone_text(zone, extract)}"
    roles_by_col = evidence["roles_by_col"]
    money_cols = evidence["money_cols"]
    reasons: list[str] = []
    mode = "passthrough"
    confidence = 0.35

    if len(set(roles_by_col.values())) >= 2:
        mode, confidence = "lattice", 0.95
        reasons.append(f"explicit_roles={','.join(roles_by_col.values())}")
    elif evidence["has_amount_header"] and len(money_cols) <= 2:
        mode, confidence = "amount_anchored", 0.95
        reasons.append("amount_php_header")
    elif len(money_cols) >= 2:
        mode, confidence = "lattice", 0.78
        reasons.append(f"numeric_columns={len(money_cols)}")
    elif len(money_cols) == 1:
        mode, confidence = "amount_anchored", 0.7
        reasons.append("single_numeric_column")
    elif YEAR_CUE.search(text) or UNIT_CUE.search(text):
        mode, confidence = "years", 0.65
        reasons.append("year_or_unit_cue")
    elif zone.get("label") in {"text", "content", "paragraph_title"}:
        mode, confidence = "prose", 0.8
        reasons.append("text_zone_without_amount_columns")
    elif zone.get("label") != "table":
        mode, confidence = "prose", 0.6
        reasons.append("non_table_zone")
    else:
        reasons.append("table_without_supported_schema_evidence")

    if mode == "passthrough" and carry and carry.get("schema_mode") in {"lattice", "amount_anchored"}:
        mode = carry["schema_mode"]
        confidence = 0.55
        reasons.append("contiguous_page_carry")

    ordered_cols = sorted(roles_by_col)
    roles = [roles_by_col[col] for col in ordered_cols]
    centers = [evidence["centers_by_col"][col] for col in sorted(evidence["centers_by_col"])]
    if mode == "lattice" and not roles:
        roles = list((carry or {}).get("col_roles") or ["PS", "MOOE", "CO", "Total"])
    if mode == "amount_anchored":
        roles = ["Amount"]
    if not centers and carry and "contiguous_page_carry" in reasons:
        centers = list(carry.get("col_centers") or [])

    decision = {
        "zone_id": zone.get("zone_id"), "region_id": zone.get("region_id"),
        "table_id": (table or {}).get("table_id"), "schema_mode": mode,
        "schema_label": "by_ou_like" if mode == "lattice" else "pap_like" if mode == "amount_anchored" else None,
        "col_roles": roles, "role_columns": {str(col): role for col, role in roles_by_col.items()},
        "col_centers": centers, "n_money_hits": evidence["n_money_hits"],
        "n_money_cols": len(money_cols), "amount_unit": "thousand_pesos" if evidence["has_unit_cue"] else "pesos",
        "confidence": round(confidence, 3), "qa_status": decision_status(confidence),
        "reasons": reasons,
    }
    return decision


def infer_page_schema(
    extract: dict[str, Any], *, carry: dict[str, Any] | None = None,
    previous_page: int | None = None,
) -> dict[str, Any]:
    validate_extract(extract)
    page = int(extract["page"])
    contiguous = previous_page is not None and page == previous_page + 1
    effective_carry = carry if contiguous else None
    zones = list(extract.get("zones") or [])
    if not zones:
        size = extract.get("page_size_pt") or [720, 864]
        zones = [{"zone_id": 0, "region_id": None, "label": "page", "bbox": [0, 0, *size]}]
    tables_by_region = {table.get("region_id"): table for table in extract.get("tables") or []}
    decisions = [infer_zone(zone, extract, table=tables_by_region.get(zone.get("region_id")), carry=effective_carry) for zone in zones]
    page_text = " ".join(str(line.get("text") or "") for line in extract.get("lines") or [] if not line.get("chrome"))
    if UNIT_CUE.search(page_text):
        for decision in decisions:
            decision["amount_unit"] = "thousand_pesos"
            decision["reasons"].append("page_unit_cue")
    elif effective_carry and effective_carry.get("amount_unit") == "thousand_pesos":
        for decision in decisions:
            decision["amount_unit"] = "thousand_pesos"
            decision["reasons"].append("contiguous_unit_carry")
    structured = [item for item in decisions if item["schema_mode"] in {"lattice", "amount_anchored", "years"}]
    primary = max(structured or decisions, key=lambda item: item["confidence"])
    findings = []
    for item in decisions:
        if item["qa_status"] != "accept":
            findings.append({"severity": item["qa_status"], "zone_id": item["zone_id"], "code": "schema_confidence", "reasons": item["reasons"]})
    artifact = {
        "page": page, "dpi": extract.get("dpi"), "schema_mode": primary["schema_mode"],
        "schema_label": primary["schema_label"], "col_roles": primary["col_roles"],
        "col_centers": primary["col_centers"], "amount_unit": primary["amount_unit"],
        "confidence": primary["confidence"], "qa_status": primary["qa_status"],
        "zone_schemas": decisions, "findings": findings,
        "sequence": {"previous_page": previous_page, "contiguous": contiguous, "carry_used": any("contiguous_page_carry" in item["reasons"] for item in decisions)},
    }
    stamp_meta(artifact, stage="schema", producer="evidence_schema_v1")
    validate_schema(artifact)
    return artifact


def run_stage(context) -> dict[str, Any]:
    results = []
    carry = None
    previous_page = None
    started_at, started = iso_now(), time.perf_counter()
    for page_no in context.pages:
        page_started_at, page_started = iso_now(), time.perf_counter()
        try:
            extract = read_json(context.store.extract_path(page_no))
            schema = infer_page_schema(extract, carry=carry, previous_page=previous_page)
            write_json_atomic(context.store.schema_path(page_no), schema)
            counts = {status: sum(item["qa_status"] == status for item in schema["zone_schemas"]) for status in ("accept", "review", "reject")}
            result = {"page": page_no, "pass": counts["reject"] == 0, "schema_mode": schema["schema_mode"], "confidence": schema["confidence"], "n_zones": len(schema["zone_schemas"]), **{f"n_{key}": value for key, value in counts.items()}, "carry_used": schema["sequence"]["carry_used"]}
            carry = schema
            previous_page = page_no
        except Exception as error:
            result = {"page": page_no, "pass": False, "error_type": type(error).__name__, "error": str(error)}
            carry = None
            previous_page = page_no
        result.update({"started_at": page_started_at, "completed_at": iso_now(), "timestamp_source": "captured", "elapsed_s": round(time.perf_counter() - page_started, 3)})
        results.append(result)
    n_fail = sum(not item["pass"] for item in results)
    summary = {"artifact_version": 1, "gate": "INFER_SCHEMA", "name": "evidence_schema_v1", "n_pages": len(results), "n_fail": n_fail, "n_review": sum(item.get("n_review", 0) for item in results), "n_reject": sum(item.get("n_reject", 0) for item in results), "started_at": started_at, "completed_at": iso_now(), "timestamp_source": "captured", "elapsed_s": round(time.perf_counter() - started, 3), "pages": results, "pass": n_fail == 0}
    write_json_atomic(context.store.stage_qa_path("schema"), summary)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    add_stage_arguments(parser)
    context = make_context(parser.parse_args())
    summary = run_stage(context)
    print(f"005.00 Schema: pages={summary['n_pages']} review={summary['n_review']} reject={summary['n_reject']} fail={summary['n_fail']} elapsed={summary['elapsed_s']}s")
    require_pass(summary)


if __name__ == "__main__":
    main()
