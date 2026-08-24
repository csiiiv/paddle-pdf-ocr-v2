from __future__ import annotations

from conftest import load_etl_node

node = load_etl_node("002.30-by-ou-tree.py")
assemble_tree = node.assemble_tree
_fit_page_centers = node._fit_page_centers


def seed_table() -> dict:
    return {
        "table_id": "by-ou-test",
        "table_type": "by_ou",
        "start": {"page": 1},
        "end": {"page": 3},
        "hierarchy_seed": {"page": 1, "phrase_id": 2,
                           "text": "A. REGULAR PROGRAMS", "level": 0},
        "carry_policy": {"contiguous_pages_only": True, "reset_on_gap": True},
    }


def phrase(phrase_id: int, band_id: int, text: str, observation: str = "text_candidate",
           **extra) -> dict:
    base = {"phrase_id": phrase_id, "band_id": band_id, "text": text,
            "observation": observation, "token_ids": [phrase_id]}
    base.update(extra)
    return base


def page_input(page: int, *, phrases: list[dict], rows: list[dict],
               cells: list[dict] | None = None,
               findings: list[dict] | None = None,
               columns: list[dict] | None = None,
               headers: list[dict] | None = None) -> dict:
    structure = {
        "table_layout": {"table_type": "by_ou", "wrap_direction": "wraps_up"},
        "row_sections": rows,
        "cell_sections": cells or [],
        "column_sections": columns or [
            {"role": "Labels", "column_section_id": 0},
            {"role": "Amount 1", "column_section_id": 1},
        ],
        "header_sections": headers or [],
        "findings": findings or [],
    }
    return {"page": page, "geometry": {"phrases": phrases}, "structure": structure}


def body_row(page: int, row_id: int, *, label: str, distance: float | None,
             amount: str = "1, 000", code_phrase: dict | None = None,
             extra_phrases: list[dict] | None = None,
             label_phrase_id: int = 100) -> tuple[dict, list[dict]]:
    phrases: list[dict] = [
        phrase(label_phrase_id, row_id, label,
               text_candidate_type="main_text_candidate",
               relative_anchor={"distance_pt": distance, "corrected_x": 0.0}),
        phrase(label_phrase_id + 1, row_id, amount, observation="money_candidate"),
    ]
    if code_phrase is not None:
        phrases.insert(0, code_phrase)
    if extra_phrases:
        phrases.extend(extra_phrases)
    row = {
        "row_section_id": row_id,
        "phrase_ids": [p["phrase_id"] for p in phrases],
        "left_of_label_phrase_ids": [code_phrase["phrase_id"]] if code_phrase else [],
        "label_left_boundary": {
            "terminal_label_phrase_id": label_phrase_id,
            "anchor_distance": distance,
        },
        "bbox": [0, 0, 100, 10],
    }
    label_ids = [label_phrase_id] + [p["phrase_id"] for p in extra_phrases or []]
    cell_ids = [p["phrase_id"] for p in phrases
                if p["observation"] != "code_candidate" and p["phrase_id"] != label_phrase_id + 1]
    cells = [
        {"cell_section_id": row_id * 2, "row_section_id": row_id,
         "column_role": "Labels", "column_section_id": 0,
         "text": label, "phrase_ids": cell_ids, "empty": not cell_ids,
         "lines": [{"band_id": row_id, "text": label, "phrase_ids": cell_ids}]},
        {"cell_section_id": row_id * 2 + 1, "row_section_id": row_id,
         "column_role": "Amount 1", "column_section_id": 1,
         "text": amount, "phrase_ids": [label_phrase_id + 1],
         "empty": not amount, "lines": [{"band_id": row_id, "text": amount,
                                         "phrase_ids": [label_phrase_id + 1]}]},
    ]
    _ = page, label_ids
    return row, cells


def collect(pages: list[dict]) -> tuple[dict, dict]:
    tree = assemble_tree(pages, table_seed=seed_table())
    return tree, {entry["id"]: entry for entry in tree["nodes"]}


def test_region_office_nesting_and_carry() -> None:
    region_row, region_cells = body_row(1, 0, label="Region I - Ilocos", distance=479.0)
    office_row, office_cells = body_row(1, 1, label="Regional Office I - Proper",
                                        distance=454.0, label_phrase_id=110)
    next_office_row, next_office_cells = body_row(
        2, 0, label="Ilocos Norte District Engineering Office",
        distance=453.5, label_phrase_id=210)
    pages = [
        page_input(1, phrases=[], rows=[region_row, office_row],
                   cells=region_cells + office_cells,
                   headers=[{"role": "table_title",
                             "text": "New Appropriations by Operating Units"}]),
        page_input(2, phrases=[], rows=[next_office_row], cells=next_office_cells),
    ]
    pages[1]["geometry"]["phrases"] = [
        phrase(210, 0, "Ilocos Norte District Engineering Office",
               text_candidate_type="main_text_candidate",
               relative_anchor={"distance_pt": 453.5}),
        phrase(211, 0, "3, 000", observation="money_candidate"),
    ]
    tree, by_id = collect(pages)
    assert by_id["p1:r0"]["kind"] == "region"
    assert by_id["p1:r1"]["kind"] == "office"
    assert by_id["p1:r1"]["parent"] == "p1:r0"
    assert by_id["p2:r0"]["parent"] == "p1:r0", "office carry must survive the page break"
    assert by_id["p1:r0"]["page"] == 1
    assert by_id["root"]["kind"] == "table_root"
    assert tree["roots"] == ["root"]


def test_program_and_activity_code_prefix_nesting() -> None:
    program_row, program_cells = body_row(
        1, 0, label="General Administration and Support", distance=478.0,
        code_phrase=phrase(90, 0, "100000000000000", observation="code_candidate"))
    activity_row, activity_cells = body_row(
        1, 1, label="General Management and Supervision", distance=477.5,
        code_phrase=phrase(91, 1, "100000100001000", observation="code_candidate"),
        label_phrase_id=110)
    pages = [page_input(1, phrases=[
        phrase(90, 0, "100000000000000", observation="code_candidate"),
        phrase(100, 0, "General Administration and Support",
               text_candidate_type="main_text_candidate",
               relative_anchor={"distance_pt": 478.0}),
        phrase(101, 0, "1, 000", observation="money_candidate"),
        phrase(91, 1, "100000100001000", observation="code_candidate"),
        phrase(110, 1, "General Management and Supervision",
               text_candidate_type="main_text_candidate",
               relative_anchor={"distance_pt": 477.5}),
        phrase(111, 1, "2, 000", observation="money_candidate"),
    ], rows=[program_row, activity_row], cells=program_cells + activity_cells)]
    tree, by_id = collect(pages)
    assert by_id["p1:r0"]["kind"] == "program"
    assert by_id["p1:r0"]["code"] == "100000000000000"
    assert by_id["p1:r1"]["kind"] == "activity"
    assert by_id["p1:r1"]["confidence"] == "code"
    # PREXC may insert a synthesized sub-program shell between program and activity.
    parent = by_id[by_id["p1:r1"]["parent"]]
    assert parent["id"] == "p1:r0" or parent.get("code") == "100000100000000"
    assert tree["algorithm"]["hierarchy"] == "prexc_code"


def test_subtotal_matches_program_label() -> None:
    program_row, program_cells = body_row(
        1, 0, label="General Administration and Support", distance=478.0,
        code_phrase=phrase(90, 0, "100000000000000", observation="code_candidate"))
    subtotal_row, subtotal_cells = body_row(
        1, 1, label="Sub-total, General Administration and Support", distance=549.6,
        label_phrase_id=110)
    pages = [page_input(1, phrases=[
        phrase(90, 0, "100000000000000", observation="code_candidate"),
        phrase(100, 0, "General Administration and Support",
               text_candidate_type="main_text_candidate",
               relative_anchor={"distance_pt": 478.0}),
        phrase(101, 0, "1, 000", observation="money_candidate"),
        phrase(110, 1, "Sub-total, General Administration and Support",
               text_candidate_type="main_text_candidate",
               relative_anchor={"distance_pt": 549.6}),
        phrase(111, 1, "1, 000", observation="money_candidate"),
    ], rows=[program_row, subtotal_row], cells=program_cells + subtotal_cells)]
    tree, by_id = collect(pages)
    subtotal = by_id["p1:r1"]
    assert subtotal["kind"] == "subtotal"
    assert subtotal["parent"] == "p1:r0"
    assert subtotal["subtotal_match"] == "label"
    assert "subtotal_parent_unmatched" not in subtotal["flags"]


def test_funding_metadata_excluded_from_hierarchy() -> None:
    project_row, project_cells = body_row(1, 0, label="Some Foreign Project", distance=478.0)
    loan_row, loan_cells = body_row(1, 1, label="Loan Proceeds", distance=449.0,
                                    label_phrase_id=110)
    pages = [page_input(1, phrases=[
        phrase(100, 0, "Some Foreign Project", text_candidate_type="main_text_candidate",
               relative_anchor={"distance_pt": 478.0}),
        phrase(101, 0, "1, 000", observation="money_candidate"),
        phrase(110, 1, "Loan Proceeds", text_candidate_type="main_text_candidate",
               relative_anchor={"distance_pt": 449.0}),
        phrase(111, 1, "2, 000", observation="money_candidate"),
    ], rows=[project_row, loan_row], cells=project_cells + loan_cells)]
    tree, by_id = collect(pages)
    loan = by_id["p1:r1"]
    assert loan["kind"] == "funding"
    assert loan["excluded"] is True
    assert loan["parent"] == "p1:r0"
    flags = [f["code"] for f in tree["page_flags"]["1"]]
    assert "funding_metadata_excluded" in flags


def test_embedded_section_header_resets_stack() -> None:
    office_row, office_cells = body_row(1, 0, label="Central Office", distance=454.0,
                                        extra_phrases=[
                                            phrase(50, 0, "B. PROJECTS",
                                                   observation="text_candidate",
                                                   text_candidate_type="wrapped_text_candidate",
                                                   relative_anchor={"distance_pt": 549.9}),
                                        ])
    region_row, region_cells = body_row(1, 1, label="Region I - Ilocos", distance=479.0,
                                        label_phrase_id=110)
    pages = [page_input(1, phrases=[
        phrase(50, 0, "B. PROJECTS", observation="text_candidate",
               text_candidate_type="wrapped_text_candidate",
               relative_anchor={"distance_pt": 549.9}),
        phrase(100, 0, "Central Office", text_candidate_type="main_text_candidate",
               relative_anchor={"distance_pt": 454.0}),
        phrase(101, 0, "1, 000", observation="money_candidate"),
        phrase(110, 1, "Region I - Ilocos", text_candidate_type="main_text_candidate",
               relative_anchor={"distance_pt": 479.0}),
        phrase(111, 1, "2, 000", observation="money_candidate"),
    ], rows=[office_row, region_row], cells=office_cells + region_cells)]
    tree, by_id = collect(pages)
    section = by_id["p1:ph50"]
    assert section["kind"] == "section"
    assert section["parent"] == "root"
    assert by_id["p1:r1"]["parent"] == "p1:ph50", "region after section must nest under it"


def test_page_gap_resets_carry() -> None:
    region_row, region_cells = body_row(1, 0, label="Region I - Ilocos", distance=479.0)
    office_row, office_cells = body_row(1, 1, label="Regional Office I - Proper",
                                        distance=454.0, label_phrase_id=110)
    orphan_office_row, orphan_cells = body_row(
        3, 0, label="Aurora District Engineering Office", distance=453.0,
        label_phrase_id=310)
    pages = [
        page_input(1, phrases=[
            phrase(100, 0, "Region I - Ilocos", text_candidate_type="main_text_candidate",
                   relative_anchor={"distance_pt": 479.0}),
            phrase(101, 0, "1, 000", observation="money_candidate"),
            phrase(110, 1, "Regional Office I - Proper",
                   text_candidate_type="main_text_candidate",
                   relative_anchor={"distance_pt": 454.0}),
            phrase(111, 1, "2, 000", observation="money_candidate"),
        ], rows=[region_row, office_row], cells=region_cells + office_cells),
        page_input(3, phrases=[
            phrase(310, 0, "Aurora District Engineering Office",
                   text_candidate_type="main_text_candidate",
                   relative_anchor={"distance_pt": 453.0}),
            phrase(311, 0, "3, 000", observation="money_candidate"),
        ], rows=[orphan_office_row], cells=orphan_cells),
    ]
    tree, by_id = collect(pages)
    assert by_id["p3:r0"]["parent"] == "root"
    flags = [f["code"] for f in tree["page_flags"]["3"]]
    assert "carry_gap_reset" in flags


def test_page_local_centers_absorb_displacement() -> None:
    # Page 77-style displacement: both clusters shift ~10pt left together.
    region_row, region_cells = body_row(1, 0, label="Region XII - SOCCSKSARGEN", distance=469.0)
    office_row, office_cells = body_row(1, 1, label="Cotabato District Engineering Office",
                                        distance=444.0, label_phrase_id=110)
    pages = [page_input(1, phrases=[
        phrase(100, 0, "Region XII - SOCCSKSARGEN",
               text_candidate_type="main_text_candidate",
               relative_anchor={"distance_pt": 469.0}),
        phrase(101, 0, "1, 000", observation="money_candidate"),
        phrase(110, 1, "Cotabato District Engineering Office",
               text_candidate_type="main_text_candidate",
               relative_anchor={"distance_pt": 444.0}),
        phrase(111, 1, "2, 000", observation="money_candidate"),
    ], rows=[region_row, office_row], cells=region_cells + office_cells)]
    tree, by_id = collect(pages)
    assert by_id["p1:r0"]["kind"] == "region"
    assert by_id["p1:r1"]["parent"] == "p1:r0"
    assert abs(by_id["p1:r0"]["center"] - 469.0) < 0.01
    assert "outside_center_tolerance" not in by_id["p1:r0"]["flags"]


def test_continuation_only_row_merges_into_previous() -> None:
    office_row, office_cells = body_row(1, 0, label="Cagayan de Oro City 1st District",
                                        distance=453.0)
    fragment_row, fragment_cells = body_row(1, 1, label="Office", distance=None,
                                            amount="", label_phrase_id=110)
    pages = [page_input(1, phrases=[
        phrase(100, 0, "Cagayan de Oro City 1st District",
               text_candidate_type="main_text_candidate",
               relative_anchor={"distance_pt": 453.0}),
        phrase(101, 0, "1, 000", observation="money_candidate"),
        phrase(110, 1, "Office", text_candidate_type="wrapped_text_candidate"),
    ], rows=[office_row, fragment_row], cells=office_cells + fragment_cells)]
    tree, by_id = collect(pages)
    assert "p1:r1" not in by_id
    assert by_id["p1:r0"]["label"] == "Cagayan de Oro City 1st District Office"
    assert "continuation_merged" in by_id["p1:r0"]["flags"]


def test_fit_page_centers_two_clusters_and_weak() -> None:
    centers, flags = _fit_page_centers([479.1, 478.9, 453.2, 453.4, 479.0, 453.9])
    assert centers["region"] == 479.0
    assert abs(centers["office"] - 453.4) < 0.01
    assert flags == []
    centers, flags = _fit_page_centers([453.0])
    assert centers == {"region": None, "office": 453.0}
    assert [f["code"] for f in flags] == ["weak_page_fit"]
    centers, flags = _fit_page_centers([])
    assert centers == {"region": None, "office": None}
    assert [f["code"] for f in flags] == ["no_distance_clusters"]


def test_grand_total_attaches_to_root() -> None:
    office_row, office_cells = body_row(1, 0, label="Central Office", distance=453.0)
    total_row, total_cells = body_row(1, 1, label="TOTAL NEW APPROPRIATIONS",
                                      distance=549.9, label_phrase_id=110)
    pages = [page_input(1, phrases=[
        phrase(100, 0, "Central Office", text_candidate_type="main_text_candidate",
               relative_anchor={"distance_pt": 453.0}),
        phrase(101, 0, "1, 000", observation="money_candidate"),
        phrase(110, 1, "TOTAL NEW APPROPRIATIONS",
               text_candidate_type="main_text_candidate",
               relative_anchor={"distance_pt": 549.9}),
        phrase(111, 1, "99, 000", observation="money_candidate"),
    ], rows=[office_row, total_row], cells=office_cells + total_cells)]
    tree, by_id = collect(pages)
    assert by_id["p1:r1"]["kind"] == "grand_total"
    assert by_id["p1:r1"]["parent"] == "root"


def test_amount_value_parsing() -> None:
    assert node._amount_value("13, 794, 990, 000") == 13794990000
    assert node._amount_value("18, 078, 293, 000") == 18078293000
    assert node._amount_value("") is None


def test_code_kind_discriminator() -> None:
    assert node._code_kind("100000000000000") == "program"
    assert node._code_kind("200000100018000") == "activity"
    assert node._code_kind("310101300003000") == "activity"
    assert node._code_kind("123") is None
    assert node._code_kind("30024110000100A") is None
