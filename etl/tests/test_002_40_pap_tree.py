from __future__ import annotations

from conftest import load_etl_node

node = load_etl_node("002.40-pap-tree.py")


def seed() -> dict:
    return {
        "table_id": "pap-test",
        "table_type": "pap",
        "start": {"page": 115},
        "end": {"page": 690},
        "distance_centers_pt": [514.6, 499.5, 482.7, 464.8, 448.6, 426.6, 409.0, 391.3],
        "funding_metadata_centers_pt": [104.7, 140.5],
        "matching_tolerance_pt": 4.0,
        "carry_policy": {"contiguous_pages_only": True, "reset_on_gap": True},
    }


def page(page_no: int, specs: list[tuple[str, float, str | None]]) -> dict:
    phrases, rows, cells = [], [], []
    for row_id, (label, distance, marker) in enumerate(specs):
        label_id, amount_id = row_id * 10 + 1, row_id * 10 + 2
        row_phrase_ids, left_ids = [label_id, amount_id], []
        if marker:
            marker_id = row_id * 10
            phrases.append({
                "phrase_id": marker_id, "band_id": row_id, "text": marker,
                "observation": "marker_candidate", "token_ids": [marker_id],
            })
            row_phrase_ids.insert(0, marker_id)
            left_ids.append(marker_id)
        phrases.extend([
            {
                "phrase_id": label_id, "band_id": row_id, "text": label,
                "observation": "text_candidate",
                "text_candidate_type": "main_text_candidate",
                "relative_anchor": {"distance_pt": distance},
                "token_ids": [label_id],
            },
            {
                "phrase_id": amount_id, "band_id": row_id, "text": "1, 000",
                "observation": "money_candidate", "token_ids": [amount_id],
            },
        ])
        rows.append({
            "row_section_id": row_id, "phrase_ids": row_phrase_ids,
            "left_of_label_phrase_ids": left_ids,
            "label_left_boundary": {
                "terminal_label_phrase_id": label_id,
                "anchor_distance": distance,
            },
            "bbox": [0, row_id * 10, 600, row_id * 10 + 9],
        })
        cells.extend([
            {
                "cell_section_id": row_id * 2, "row_section_id": row_id,
                "column_section_id": 0, "column_role": "Labels",
                "text": label, "phrase_ids": [label_id], "empty": False,
            },
            {
                "cell_section_id": row_id * 2 + 1, "row_section_id": row_id,
                "column_section_id": 1, "column_role": "Amount 1",
                "text": "1, 000", "phrase_ids": [amount_id], "empty": False,
            },
        ])
    return {
        "page": page_no,
        "geometry": {"phrases": phrases},
        "structure": {
            "table_layout": {"table_type": "pap", "wrap_direction": "wraps_down"},
            "row_sections": rows, "cell_sections": cells,
            "column_sections": [
                {"column_section_id": 0, "role": "Labels"},
                {"column_section_id": 1, "role": "Amount 1"},
            ],
            "findings": [],
        },
    }


def by_id(tree: dict) -> dict:
    return {item["id"]: item for item in tree["nodes"]}


def test_expense_section_and_geometric_stack() -> None:
    tree = node.assemble_tree([page(115, [
        ("MAINTENANCE AND OTHER OPERATING EXPENSES", 514.4, None),
        ("SUPPORT TO OPERATIONS", 514.8, None),
        ("National Capital Region", 501.1, None),
        ("Central Office", 482.4, None),
        ("Asset Preservation Program", 464.5, None),
        ("Region I", 448.6, None),
        ("Ilocos Norte District Engineering Office", 426.7, None),
        ("Road Project", 391.2, None),
    ])], table_seed=seed())
    nodes = by_id(tree)
    assert nodes["p115:r0"]["kind"] == "expense_class"
    assert nodes["p115:r1"]["kind"] == "section"
    assert nodes["p115:r1"]["parent"] == "p115:r0"
    assert nodes["p115:r7"]["parent"] == "p115:r6"
    assert nodes["p115:r7"]["kind"] == "project"


def test_same_visual_level_marker_is_child_of_section() -> None:
    tree = node.assemble_tree([page(115, [
        ("CAPITAL OUTLAYS", 514.1, None),
        ("SUPPORT TO OPERATIONS", 515.1, None),
        ("Pre-Feasibility Study", 516.6, "a."),
        ("National Capital Region", 501.8, None),
        ("Central Office", 483.5, None),
    ])], table_seed=seed())
    nodes = by_id(tree)
    assert nodes["p115:r2"]["parent"] == "p115:r1"
    assert nodes["p115:r3"]["parent"] == "p115:r2"
    assert nodes["p115:r2"]["marker"] == "a."


def test_leading_marker_inside_label_is_also_recognized() -> None:
    tree = node.assemble_tree([page(115, [
        ("CAPITAL OUTLAYS", 514.1, None),
        ("SUPPORT TO OPERATIONS", 515.1, None),
        ("b. Payments of Right-Of-Way", 515.4, None),
    ])], table_seed=seed())
    nodes = by_id(tree)
    assert nodes["p115:r2"]["marker"] == "b."
    assert nodes["p115:r2"]["parent"] == "p115:r1"


def test_compressed_far_left_levels_remain_distinct() -> None:
    views = [
        {"distance": distance, "funding": False}
        for distance in (500.9, 491.737, 481.4, 464.133, 447.49, 408.645, 391.153)
    ]
    _, _, clusters = node._page_centers(views, seed()["distance_centers_pt"])
    assert [item["rank"] for item in clusters] == [0, 1, 2, 3, 4, 6, 7]
    tree = node.assemble_tree([page(115, [
        ("CAPITAL OUTLAYS", 500.9, None),
        ("National Capital Region", 491.737, None),
        ("Central Office", 481.4, None),
        ("ORGANIZATIONAL OUTCOME 1", 464.133, None),
        ("Asset Preservation Program", 447.49, None),
        ("Preventive Maintenance", 408.645, None),
        ("Road Project", 391.153, None),
    ])], table_seed=seed())
    assert "formatting_displacement" in [
        item["code"] for item in tree["page_flags"]["115"]]


def test_funding_metadata_attaches_without_changing_stack() -> None:
    tree = node.assemble_tree([page(115, [
        ("CAPITAL OUTLAYS", 514.1, None),
        ("FOREIGN-ASSISTED PROJECTS", 500.9, None),
        ("National Capital Region", 491.7, None),
        ("Central Office", 481.4, None),
        ("GOP", 104.7, None),
        ("Loan Proceeds", 140.5, None),
        ("ORGANIZATIONAL OUTCOME 1", 464.1, None),
    ])], table_seed=seed())
    nodes = by_id(tree)
    assert nodes["p115:r4"]["kind"] == "funding"
    assert nodes["p115:r4"]["excluded"] is True
    assert nodes["p115:r4"]["parent"] == "p115:r3"
    assert nodes["p115:r6"]["parent"] == "p115:r3"
    assert [item["code"] for item in tree["page_flags"]["115"]].count(
        "funding_metadata_excluded") == 2


def test_merged_funding_and_terminal_open_stack_are_flagged() -> None:
    tree = node.assemble_tree([page(690, [
        ("CAPITAL OUTLAYS", 514.1, None),
        ("GOP Loan Proceeds", 104.7, None),
    ])], table_seed=seed())
    nodes = by_id(tree)
    assert "merged_funding_label" in nodes["p690:r1"]["flags"]
    codes = [item["code"] for item in tree["page_flags"]["690"]]
    assert "merged_funding_label" in codes
    assert "end_of_span_open_stack" in codes


def test_cross_page_carry_and_gap_reset() -> None:
    first = page(115, [
        ("CAPITAL OUTLAYS", 514.1, None),
        ("OPERATIONS", 513.1, None),
        ("Region I", 448.6, None),
    ])
    contiguous = page(116, [
        ("Ilocos Norte District Engineering Office", 426.6, None),
        ("Road Project", 391.3, None),
    ])
    tree = node.assemble_tree([first, contiguous], table_seed=seed())
    nodes = by_id(tree)
    assert nodes["p116:r0"]["parent"] == "p115:r2"

    gap = page(118, [("Road Project", 391.3, None)])
    tree = node.assemble_tree([first, gap], table_seed=seed())
    nodes = by_id(tree)
    assert nodes["p118:r0"]["parent"] == "root"
    assert "carry_gap_reset" in [
        item["code"] for item in tree["page_flags"]["118"]]


def test_amount_parser_and_rank_fallback() -> None:
    assert node._amount_value("117, 749, 011, 000") == 117749011000
    assert node._amount_value("") is None
    assert node._nearest_rank(391.5, seed()["distance_centers_pt"]) == 7
    assert node._nearest_rank(None, seed()["distance_centers_pt"]) is None
