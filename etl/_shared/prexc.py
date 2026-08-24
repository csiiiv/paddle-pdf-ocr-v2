"""PREXC (enhanced 15-digit UACS P/A/P) helpers for By-OU hierarchy.

Digit layout confirmed against NEP Volume 2B DPWH By-OU codes (see
docs/prexc_code.md):

  1       cost structure / purpose
  2–3     organizational outcome
  4–5     program
  6       sub-program (narrow field; ETL also uses digits 1–6 as program prefix)
  7       identifier — 1 Activity, 2 Locally Funded Project, 3 Foreign-Assisted
  8–12    lowest-level activity / project
  13–15   reserved

Hierarchy parents are the longest proper zero-padded prefix at the cumulative
cuts below. Uncoded children (region, office, …) keep whatever parent the
layout pass assigned.
"""
from __future__ import annotations

from typing import Any

CODE_LENGTH = 15
# Cumulative ends used to walk ancestors (includes the 6-digit program prefix).
PREXC_CUTS = (1, 3, 5, 6, 7, 8, 13)
PROJECT_IDENTIFIERS = frozenset({"2", "3"})
COST_LABELS = {
    "1": "General Administration and Support",
    "2": "Support to Operations",
    "3": "Operations",
    "4": "Special Purpose Funds",
}


def is_prexc_code(value: Any) -> bool:
    text = str(value or "").strip()
    return text.isdigit() and len(text) == CODE_LENGTH


def pad_code(prefix: str, length: int = CODE_LENGTH) -> str:
    prefix = str(prefix or "")
    if len(prefix) >= length:
        return prefix[:length]
    return prefix + ("0" * (length - len(prefix)))


def parse_prexc(code: str) -> dict[str, str] | None:
    if not is_prexc_code(code):
        return None
    code = str(code).strip()
    return {
        "prexc_code": code,
        "cost_structure": code[0:1],
        "organizational_outcome": code[1:3],
        "program": code[3:5],
        "subprogram": code[5:6],
        "identifier": code[6:7],
        "activity_project": code[7:12],
        "reserved": code[12:15],
    }


def identifier_digit(code: str) -> str | None:
    parsed = parse_prexc(code)
    return None if parsed is None else parsed["identifier"]


def is_project_code(code: str) -> bool:
    """True for LFP (2) / FAP (3) identifier digits."""
    return identifier_digit(code) in PROJECT_IDENTIFIERS


def ancestor_codes(code: str) -> list[str]:
    """Proper PREXC ancestors, nearest last."""
    if not is_prexc_code(code):
        return []
    code = str(code).strip()
    out: list[str] = []
    seen: set[str] = set()
    for end in PREXC_CUTS:
        parent = pad_code(code[:end])
        if parent == code or parent in seen or parent == "0" * CODE_LENGTH:
            continue
        seen.add(parent)
        out.append(parent)
    return out


def _shell_kind_label(code: str) -> tuple[str, str]:
    parts = parse_prexc(code)
    assert parts is not None
    if code[1:] == "0" * (CODE_LENGTH - 1):
        return "prexc_cost", COST_LABELS.get(parts["cost_structure"],
                                            f"Cost structure {parts['cost_structure']}")
    if code[3:] == "0" * (CODE_LENGTH - 3):
        return "prexc_oo", f"Organizational Outcome {parts['organizational_outcome']}"
    if code[5:] == "0" * (CODE_LENGTH - 5):
        return "prexc_program", f"Program {parts['program']}"
    if code[6:] == "0" * (CODE_LENGTH - 6):
        return "prexc_subprogram", f"Sub-program {parts['subprogram']}"
    if code[7:] == "0" * (CODE_LENGTH - 7):
        return "prexc_identifier", f"Identifier {parts['identifier']}"
    return "prexc_shell", f"PREXC {code}"


def _rebuild_children(nodes_by_id: dict[str, dict[str, Any]]) -> None:
    for node in nodes_by_id.values():
        node["children"] = []
    for node in nodes_by_id.values():
        parent_id = node.get("parent")
        if parent_id and parent_id in nodes_by_id:
            nodes_by_id[parent_id]["children"].append(node["id"])


def compute_prexc_parents(
    nodes: list[dict[str, Any]], *, synthesize_missing: bool = False,
) -> dict[str, str | None]:
    """Return node id -> parent id for PREXC reparenting (optional synthesis)."""
    nodes_by_id = {str(node["id"]): node for node in nodes if not node.get("synthetic")}
    code_index: dict[str, str] = {}
    for node in nodes_by_id.values():
        code = str(node.get("code") or "").strip()
        if is_prexc_code(code):
            code_index[code] = str(node["id"])

    if synthesize_missing:
        needed: set[str] = set()
        for code in list(code_index):
            for ancestor in ancestor_codes(code):
                if ancestor not in code_index:
                    needed.add(ancestor)
        for code in sorted(needed):
            kind, label = _shell_kind_label(code)
            node_id = f"prexc:{code}"
            nodes_by_id[node_id] = {
                "id": node_id, "parent": None, "kind": kind, "label": label,
                "code": code, "synthetic": True, "children": [],
            }
            code_index[code] = node_id

    def resolve_parent(code: str) -> str | None:
        for ancestor in reversed(ancestor_codes(code)):
            if ancestor in code_index:
                return code_index[ancestor]
        return None

    parents: dict[str, str | None] = {}
    for node_id, node in nodes_by_id.items():
        if node.get("synthetic"):
            code = str(node.get("code") or "").strip()
            parents[node_id] = resolve_parent(code) if is_prexc_code(code) else None
            continue
        code = str(node.get("code") or "").strip()
        if is_prexc_code(code):
            parents[node_id] = resolve_parent(code) or node.get("parent")
        else:
            parents[node_id] = node.get("parent")
    return parents


def apply_prexc_hierarchy(
    nodes: list[dict[str, Any]], *, synthesize_missing: bool = True,
) -> dict[str, Any]:
    """Reparent coded nodes by PREXC; keep uncoded children on their parents.

    Returns diagnostics about rewires and synthesized shells.
    """
    nodes_by_id = {str(node["id"]): node for node in nodes}
    parents = compute_prexc_parents(nodes, synthesize_missing=synthesize_missing)

    synthesized = [node_id for node_id, node in nodes_by_id.items() if node.get("synthetic")]
    if synthesize_missing:
        existing = set(nodes_by_id)
        for node_id, parent in parents.items():
            if node_id.startswith("prexc:") and node_id not in existing:
                code = node_id.split(":", 1)[1]
                kind, label = _shell_kind_label(code)
                node = {
                    "id": node_id,
                    "parent": parent,
                    "kind": kind,
                    "tier": None,
                    "label": label,
                    "code": code,
                    "page": None,
                    "row_section_id": None,
                    "phrase_ids": [],
                    "label_phrase_ids": [],
                    "token_ids": [],
                    "bbox": None,
                    "distance": None,
                    "center": None,
                    "delta": None,
                    "confidence": "prexc",
                    "amounts": {},
                    "total": None,
                    "flags": ["prexc_synthesized"],
                    "synthetic": True,
                    "children": [],
                }
                nodes.append(node)
                nodes_by_id[node_id] = node
                synthesized.append(node_id)

    reparented = 0
    for node in nodes:
        node_id = str(node["id"])
        if node_id not in parents:
            continue
        new_parent = parents[node_id]
        if node.get("parent") != new_parent:
            reparented += 1
        node["parent"] = new_parent
        if node.get("synthetic") or not is_prexc_code(node.get("code")):
            continue
        flags = node.setdefault("flags", [])
        if "prexc_parent" not in flags:
            flags.append("prexc_parent")

    _rebuild_children(nodes_by_id)
    coded = sum(1 for node in nodes if is_prexc_code(node.get("code")) and not node.get("synthetic"))
    return {
        "n_coded": coded,
        "n_synthesized": len(synthesized),
        "n_reparented": reparented,
        "synthesized_ids": synthesized,
    }
