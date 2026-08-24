from __future__ import annotations

from conftest import load_etl_node

node = load_etl_node("002.50-tree-totals.py")


def amount(value: int | None) -> dict | None:
    return None if value is None else {
        "role": "Total", "text": f"{value:,}", "value": value}


def tree(nodes: list[dict], *, requested: list[int] | None = None,
         reviewed_end: int = 2) -> dict:
    return {
        "algorithm": {"name": "test_tree", "version": 1},
        "table": {
            "table_id": "test-001", "table_type": "test",
            "requested_pages": requested or [1, 2],
            "reviewed_span": {"start_page": 1, "end_page": reviewed_end},
        },
        "nodes": nodes,
    }


def item(node_id: str, page: int, value: int | None, *,
         children: list[str] | None = None, kind: str = "group",
         excluded: bool = False) -> dict:
    return {
        "id": node_id, "page": page, "label": node_id, "kind": kind,
        "children": children or [], "total": amount(value),
        "excluded": excluded,
    }


def test_exact_immediate_child_sum_passes() -> None:
    result = node.validate_tree(tree([
        item("parent", 1, 100, children=["a", "b"]),
        item("a", 1, 40), item("b", 1, 60),
    ]), selected_pages={1})
    check = result["checks"][0]
    assert check["status"] == "pass"
    assert check["child_sum"] == 100
    assert check["difference"] == 0


def test_mismatch_retains_signed_difference() -> None:
    result = node.validate_tree(tree([
        item("parent", 1, 100, children=["a", "b"]),
        item("a", 1, 40), item("b", 1, 50),
    ]), selected_pages={1})
    check = result["checks"][0]
    assert check["status"] == "mismatch"
    assert check["difference"] == 10
    assert result["diagnostics"]["n_mismatch"] == 1


def test_explicit_subtotal_is_excluded_to_avoid_double_counting() -> None:
    result = node.validate_tree(tree([
        item("parent", 1, 100, children=["detail", "subtotal"]),
        item("detail", 1, 100),
        item("subtotal", 1, 100, kind="subtotal"),
    ]), selected_pages={1})
    check = result["checks"][0]
    assert check["status"] == "pass"
    assert check["n_excluded_children"] == 1
    assert check["excluded_children"][0]["reason"] == "semantic_aggregate"


def test_funding_metadata_is_excluded_from_child_sum() -> None:
    result = node.validate_tree(tree([
        item("region", 1, 100, children=["office", "gop", "loan"]),
        item("office", 1, 100, kind="office"),
        item("gop", 1, 40, kind="funding", excluded=True),
        item("loan", 1, 60, kind="funding", excluded=True),
    ]), selected_pages={1})
    check = result["checks"][0]
    assert check["status"] == "pass"
    assert check["n_additive_children"] == 1
    assert check["n_excluded_children"] == 2
    assert {row["reason"] for row in check["excluded_children"]} == {"funding_metadata"}


def test_prexc_project_siblings_are_excluded_from_program_rollup() -> None:
    result = node.validate_tree(tree([
        {
            "id": "prog", "page": 1, "label": "Program", "kind": "program",
            "code": "310101000000000", "children": ["act", "fap"],
            "total": amount(100),
        },
        {
            "id": "act", "page": 1, "label": "Activity", "kind": "activity",
            "code": "310101100238000", "children": [], "total": amount(100),
        },
        {
            "id": "fap", "page": 1, "label": "Foreign project", "kind": "activity",
            "code": "310101300003000", "children": [], "total": amount(50),
        },
    ]), selected_pages={1})
    check = result["checks"][0]
    assert check["status"] == "pass"
    assert check["n_additive_children"] == 1
    assert check["n_excluded_children"] == 1
    assert check["excluded_children"][0]["reason"] == "prexc_project_sibling"


def test_missing_child_amount_prevents_comparison() -> None:
    result = node.validate_tree(tree([
        item("parent", 1, 100, children=["a", "b"]),
        item("a", 1, 100), item("b", 1, None),
    ]), selected_pages={1})
    check = result["checks"][0]
    assert check["status"] == "incomplete_children"
    assert check["missing_child_amount_ids"] == ["b"]


def test_partial_last_page_subtree_is_boundary_incomplete() -> None:
    result = node.validate_tree(tree([
        item("parent", 1, 100, children=["child"]),
        item("child", 2, 90),
    ], requested=[1, 2], reviewed_end=3), selected_pages={1})
    check = result["checks"][0]
    assert check["status"] == "boundary_incomplete"
    assert check["boundary_incomplete"] is True
    assert result["diagnostics"]["partial_artifact"] is True


def test_partial_boundary_cannot_hide_child_overcount() -> None:
    result = node.validate_tree(tree([
        item("parent", 1, 100, children=["child"]),
        item("child", 2, 110),
    ], requested=[1, 2], reviewed_end=3), selected_pages={1})
    check = result["checks"][0]
    assert check["status"] == "mismatch"
    assert check["boundary_incomplete"] is True
    assert check["difference"] == -10


def test_only_selected_parent_pages_are_checked() -> None:
    result = node.validate_tree(tree([
        item("p1", 1, 10, children=["a"]), item("a", 1, 10),
        item("p2", 2, 20, children=["b"]), item("b", 2, 20),
    ]), selected_pages={2})
    assert [check["parent_id"] for check in result["checks"]] == ["p2"]


def test_absolute_tolerance_is_inclusive() -> None:
    result = node.validate_tree(tree([
        item("parent", 1, 100, children=["a"]),
        item("a", 1, 99),
    ]), selected_pages={1}, absolute_tolerance=1)
    assert result["checks"][0]["status"] == "pass"
