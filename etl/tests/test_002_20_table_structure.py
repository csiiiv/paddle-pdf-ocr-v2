from __future__ import annotations

from conftest import load_etl_node

node = load_etl_node("002.20-table-structure.py")
derive_table_sections = node.derive_table_sections


def phrase(phrase_id: int, band_id: int, text: str, bbox: list[float],
           observation: str = "text_candidate") -> dict:
    return {"phrase_id": phrase_id, "band_id": band_id, "text": text,
            "bbox": bbox, "token_ids": [phrase_id], "observation": observation}


def geometry() -> dict:
    return {
        "page_size_pt": [600, 200],
        "phrases": [
            phrase(0, 0, "ROOT", [20, 11, 70, 20]),
            phrase(1, 1, "Wrapped label", [30, 25, 160, 35]),
            phrase(2, 2, "First row", [40, 42, 120, 50]) | {
                "text_candidate_type": "main_text_candidate",
                "aligned_amount_phrase_ids": [3],
                "relative_anchor": {"corrected_x": 40.0, "distance_pt": 510.0},
            },
            phrase(3, 2, "1,000", [500, 41, 550, 50], "money_candidate"),
            phrase(4, 3, "Second row", [40, 82, 120, 90]) | {
                "text_candidate_type": "main_text_candidate",
                "aligned_amount_phrase_ids": [5],
                "relative_anchor": {"corrected_x": 40.0, "distance_pt": 510.0},
            },
            phrase(5, 3, "2,000", [500, 81, 550, 90], "money_candidate"),
        ],
        "baseline_bands": [
            {"band_id": 0, "baseline_y": 20, "baseline_segment": [20, 20, 70, 20]},
            {"band_id": 2, "baseline_y": 50, "baseline_segment": [0, 50, 600, 50]},
            {"band_id": 3, "baseline_y": 90, "baseline_segment": [0, 90, 600, 90]},
        ],
        "column_candidates": [{
            "column_id": 0, "recurring": True,
            "left_line_segment": [450, 0, 452, 200],
        }],
        "fit_candidates": [
            {"column_id": 0, "pair_phrase_ids": [[2, 3], [4, 5]],
             "segments": [[120, 50, 550, 49], [120, 90, 550, 89]]},
            {"column_id": 1, "pair_phrase_ids": [[2, 6], [4, 7]],
             "segments": [[120, 50, 580, 50], [120, 90, 580, 90]]},
        ],
    }


def test_two_column_sections_use_leftmost_amount_edge() -> None:
    result = derive_table_sections(geometry(), root_band_id=0, root_source="reviewed")
    assert [section["role"] for section in result["column_sections"]] == ["Labels", "Amount 1"]
    labels, amounts = result["column_sections"]
    assert labels["phrase_ids"] == [0, 1, 2, 4]
    assert amounts["phrase_ids"] == [3, 5]
    assert labels["polygon"][1][0] == 450.0
    assert labels["polygon"][2][0] == 452.0


def test_every_amount_candidate_gets_an_explicit_column_section() -> None:
    sample = geometry()
    sample["column_candidates"] = [
        {"column_id": index, "recurring": True,
         "left_line_segment": [x, 0, x + 2, 200]}
        for index, x in enumerate((300, 380, 460, 540))
    ]
    result = derive_table_sections(
        sample, root_band_id=0, root_source="reviewed",
        column_roles={0: "PS", 1: "MOOE", 2: "CO", 3: "Total"})
    assert [section["role"] for section in result["column_sections"]] == [
        "Labels", "PS", "MOOE", "CO", "Total",
    ]
    assert [section["source_column_candidate_id"] for section in result["column_sections"]] == [
        None, 0, 1, 2, 3,
    ]


def test_sparse_non_recurring_amount_column_is_retained() -> None:
    """Sparse CO between MOOE and Total must not collapse into one cell."""
    sample = geometry()
    sample["column_candidates"] = [
        {"column_id": 0, "recurring": True, "left_line_segment": [300, 0, 302, 200]},
        {"column_id": 1, "recurring": True, "left_line_segment": [380, 0, 382, 200]},
        {"column_id": 2, "recurring": False, "left_line_segment": [460, 0, 462, 200]},
        {"column_id": 3, "recurring": True, "left_line_segment": [540, 0, 542, 200]},
    ]
    # Move the fixture's single amount into Total; add PS/MOOE/CO beside it.
    sample["phrases"][3]["bbox"] = [550, 41, 590, 50]
    sample["phrases"][5]["bbox"] = [550, 81, 590, 90]
    sample["phrases"].extend([
        phrase(6, 2, "100", [310, 41, 350, 50], "money_candidate"),
        phrase(7, 2, "200", [390, 41, 430, 50], "money_candidate"),
        phrase(8, 2, "300", [470, 41, 510, 50], "money_candidate"),
    ])
    result = derive_table_sections(
        sample, root_band_id=0, root_source="reviewed",
        column_roles={0: "PS", 1: "MOOE", 2: "CO", 3: "Total"})
    assert [section["role"] for section in result["column_sections"]] == [
        "Labels", "PS", "MOOE", "CO", "Total",
    ]
    assert result["column_sections"][3]["sparse"] is True
    assert not any(finding["code"] == "sparse_amount_column"
                   for finding in result["findings"])
    row0 = [cell for cell in result["cell_sections"] if cell["row_section_id"] == 0]
    by_role = {cell["column_role"]: cell for cell in row0}
    assert by_role["PS"]["phrase_ids"] == [6]
    assert by_role["MOOE"]["phrase_ids"] == [7]
    assert by_role["CO"]["phrase_ids"] == [8]
    assert by_role["Total"]["phrase_ids"] == [3]
    assert not any(finding["code"] == "multiple_money_candidates_in_cell"
                   for finding in result["findings"])


def test_label_column_starts_at_leftmost_main_text_anchor() -> None:
    sample = geometry()
    sample["phrases"][2]["text_candidate_type"] = "main_text_candidate"
    sample["phrases"][2]["relative_anchor"] = {"corrected_x": 40.0, "distance_pt": 510.0}
    sample["column_candidates"][0].update({
        "right_x_reference_y": 100.0, "drift_slope_dx_dy": 0.01,
    })
    result = derive_table_sections(sample, root_band_id=0, root_source="reviewed")
    labels = result["column_sections"][0]
    assert labels["left_boundary_source"] == "main_text_anchor_distance_envelope"
    assert labels["polygon"][0][0] == 39.0
    assert labels["polygon"][3][0] == 41.0


def test_main_text_candidates_become_row_boundaries() -> None:
    result = derive_table_sections(geometry(), root_band_id=0, root_source="reviewed")
    alignments = [boundary for boundary in result["row_boundaries"]
                  if boundary["kind"] == "main_text_boundary"]
    assert len(alignments) == 2
    assert alignments[0]["label_phrase_id"] == 2
    assert alignments[0]["amount_phrase_ids"] == [3]
    assert alignments[0]["kind"] == "main_text_boundary"
    assert alignments[0]["source"] == "main_text_candidate_band_baseline"


def test_rows_run_from_root_to_fits_to_page_bottom() -> None:
    result = derive_table_sections(geometry(), root_band_id=0, root_source="reviewed")
    rows = result["row_sections"]
    assert len(rows) == 3
    assert rows[0]["top_boundary_id"] == "root"
    assert rows[0]["bottom_boundary_id"] == 0
    assert rows[-1]["bottom_boundary_id"] == "page_bottom"
    assert rows[0]["phrase_ids"] == [1, 2, 3]
    assert rows[1]["phrase_ids"] == [4, 5]
    assert rows[2]["phrase_ids"] == []


def test_pap_rows_own_wrapped_text_below_the_main_line() -> None:
    sample = geometry()
    sample["phrases"][4]["band_id"] = 4
    sample["phrases"][5]["band_id"] = 4
    sample["baseline_bands"][2]["band_id"] = 4
    sample["phrases"].append(phrase(6, 3, "Wrapped below", [40, 60, 150, 70]))
    result = derive_table_sections(
        sample, wrap_direction="wraps_down", table_type="pap",
        layout_source="test")
    rows = result["row_sections"]
    assert len(rows) == 2
    assert rows[0]["row_wrap_direction"] == "wraps_down"
    assert rows[0]["phrase_ids"] == [2, 3, 6]
    assert rows[0]["label_left_boundary"]["terminal_label_phrase_id"] == 2


def test_cell_sections_intersect_rows_and_columns_and_preserve_lines() -> None:
    result = derive_table_sections(geometry(), root_band_id=0, root_source="reviewed")
    cells = result["cell_sections"]
    assert len(cells) == 6
    first_label, first_amount = cells[0], cells[1]
    assert (first_label["row_section_id"], first_label["column_role"]) == (0, "Labels")
    assert first_label["phrase_ids"] == [1, 2]
    assert first_label["text"] == "Wrapped label\nFirst row"
    assert first_label["flat_text"] == "Wrapped label First row"
    assert first_amount["phrase_ids"] == [3]
    assert first_amount["text"] == "1,000"
    assert cells[-1]["empty"] is True


def test_reviewed_header_specs_create_distinct_header_sections() -> None:
    sample = geometry()
    sample["baseline_bands"].extend([
        {"band_id": 4, "baseline_y": 8, "bbox": [20, 1, 580, 8], "phrase_ids": []},
        {"band_id": 5, "baseline_y": 12, "bbox": [20, 9, 580, 12], "phrase_ids": []},
    ])
    result = derive_table_sections(sample, root_band_id=0, root_source="reviewed",
        header_specs=[{"role": "page_header", "band_ids": [4]},
                      {"role": "column_headers", "band_ids": [5]}])
    assert [section["role"] for section in result["header_sections"]] == [
        "page_header", "column_headers",
    ]
    assert result["header_sections"][0]["polygon"] == [
        [0.0, 1.0], [600.0, 1.0], [600.0, 8.0], [0.0, 8.0],
    ]


def test_label_indent_excludes_code_phrase_from_cell_text() -> None:
    sample = geometry()
    sample["phrases"][1].update({"text": "Label", "bbox": [40, 25, 70, 35]})
    sample["phrases"].append(phrase(6, 1, "100000000000000", [10, 25, 25, 35],
                                    "code_candidate"))
    result = derive_table_sections(sample, root_band_id=0, root_source="reviewed")
    assert result["row_sections"][0]["label_left_boundary"]["source"] == "main_text_bbox_left"
    assert result["row_sections"][0]["left_of_label_phrase_ids"] == [6]
    assert result["row_sections"][0]["left_of_label_token_ids"] == [6]
    assert result["cell_sections"][0]["text"] == "Label\nFirst row"
    assert result["cell_sections"][0]["phrase_ids"] == [1, 2]


def test_missing_amount_columns_and_fits_are_review_findings() -> None:
    result = derive_table_sections({"page_size_pt": [600, 200], "phrases": []})
    assert result["column_sections"] == []
    assert result["row_sections"] == []
    assert {finding["code"] for finding in result["findings"]} == {
        "no_recurring_amount_column", "no_main_text_boundaries",
    }
