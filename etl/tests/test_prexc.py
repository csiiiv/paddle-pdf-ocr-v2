"""PREXC digit grammar and By-OU hierarchy reparenting."""
from __future__ import annotations

from _shared.prexc import (
    ancestor_codes,
    apply_prexc_hierarchy,
    compute_prexc_parents,
    is_project_code,
    parse_prexc,
)


def test_parse_prexc_15_digit_fields() -> None:
    parts = parse_prexc("310101100238000")
    assert parts is not None
    assert parts["cost_structure"] == "3"
    assert parts["organizational_outcome"] == "10"
    assert parts["program"] == "10"
    assert parts["subprogram"] == "1"
    assert parts["identifier"] == "1"
    assert parts["activity_project"] == "00238"
    assert parts["reserved"] == "000"


def test_project_identifier_digits() -> None:
    assert not is_project_code("310101100238000")
    assert is_project_code("310101300003000")
    assert is_project_code("300105201793000")


def test_ancestor_codes_include_six_digit_program_prefix() -> None:
    ancestors = ancestor_codes("310101100238000")
    assert "310101000000000" in ancestors
    assert "310100000000000" in ancestors
    assert "300000000000000" in ancestors


def test_compute_prexc_parents_without_synthesis() -> None:
    nodes = [
        {"id": "root", "parent": None, "kind": "table_root", "code": None},
        {"id": "gas", "parent": "root", "kind": "program", "code": "100000000000000"},
        {"id": "act", "parent": "root", "kind": "activity", "code": "100000100001000"},
    ]
    parents = compute_prexc_parents(nodes, synthesize_missing=False)
    assert parents["act"] == "gas"


def test_apply_prexc_keeps_uncoded_children_on_coded_parent() -> None:
    nodes = [
        {"id": "root", "parent": None, "kind": "table_root", "code": None, "children": []},
        {"id": "sec", "parent": "root", "kind": "section", "code": None, "label": "A.",
         "children": []},
        {"id": "prog", "parent": "sec", "kind": "program", "code": "100000000000000",
         "label": "GAS", "children": [], "flags": []},
        {"id": "act", "parent": "sec", "kind": "activity", "code": "100000100001000",
         "label": "GMS", "children": [], "flags": []},
        {"id": "region", "parent": "act", "kind": "region", "code": None,
         "label": "NCR", "children": [], "flags": []},
        {"id": "office", "parent": "region", "kind": "office", "code": None,
         "label": "Central Office", "children": [], "flags": []},
    ]
    stats = apply_prexc_hierarchy(nodes, synthesize_missing=True)
    by_id = {node["id"]: node for node in nodes}
    # Activity nests under GAS via optional synthesized sub-program shell.
    act_parent = by_id[by_id["act"]["parent"]]
    assert act_parent["id"] == "prog" or act_parent.get("code") == "100000100000000"
    assert by_id["region"]["parent"] == "act"
    assert by_id["office"]["parent"] == "region"
    assert "region" in by_id["act"]["children"]
    assert stats["n_reparented"] >= 1
    assert stats["n_synthesized"] >= 1
    # Walk to the real GAS program.
    cursor = by_id["act"]
    seen = set()
    while cursor["id"] not in seen and cursor.get("parent"):
        seen.add(cursor["id"])
        cursor = by_id[cursor["parent"]]
        if cursor.get("code") == "100000000000000":
            break
    assert cursor.get("code") == "100000000000000"
