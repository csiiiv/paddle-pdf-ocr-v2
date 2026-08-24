from __future__ import annotations

from conftest import load_etl_node

node = load_etl_node("002.10-token-geometry.py")
derive_token_geometry = node.derive_token_geometry


def tok(text: str, bbox: list[float], line_id: int) -> dict:
    return {"text": text, "bbox": bbox, "line_id": line_id, "source": "paddle"}


def test_bottom_aligned_tokens_form_a_band_and_marker_fragment() -> None:
    tokens = [
        tok("a", [100, 20, 103, 29], 7), tok(".", [104, 20, 108, 29], 7),
        tok("Infrastructure", [118, 19, 174, 29], 7),
        tok("Planning", [175, 19, 210, 29], 7),
        tok("12,345,000", [500, 20, 560, 29], 8),
    ]
    result = derive_token_geometry(tokens, page_size=[600, 800])
    assert len(result["baseline_bands"]) == 1
    assert [p["text"] for p in result["phrases"]] == ["a.", "Infrastructure Planning", "12,345,000"]
    assert result["phrases"][0]["observation"] == "marker_candidate"
    assert result["phrases"][2]["observation"] == "money_candidate"
    assert result["baseline_bands"][0]["source_line_ids"] == [7, 8]
    assert result["gaps"][1]["reason"] in {"marker_raw_gap", "marker_compensated_gap"}
    assert result["gaps"][1]["compensated_gap_pt"] > 0
    assert result["diagnostics"]["mean_assignment_confidence"] > .9


def test_recurring_right_aligned_amount_column_is_measured_not_classified() -> None:
    tokens = []
    for row, y in enumerate((20, 40, 60)):
        tokens.extend([tok(f"Label{row}", [100, y, 180, y + 9], row), tok(f"{row + 1},000,000", [500, y, 560, y + 9], row)])
    result = derive_token_geometry(tokens, page_size=[600, 100])
    assert result["column_candidates"][0]["right_x"] == 560
    assert result["column_candidates"][0]["recurring"] is True
    assert result["column_candidates"][0]["review"] is False
    assert result["fit_candidates"][0]["n_pairs"] == 3
    assert result["column_candidates"][0]["amount_left_x"] == 500
    assert result["label_indent_anchors"][0]["n_phrases"] == 3
    assert result["phrases"][0]["relative_anchor"] == {
        "alignment_edge": "left", "raw_x": 100.0, "corrected_x": 100.0,
        "reference_right_x": 560.0, "distance_pt": 460.0,
        "reference_support": "rightmost_recurring_amount_anchor",
        "drift_slope_dx_dy": 0.0,
    }
    assert result["phrases"][1]["relative_anchor"]["distance_pt"] == 0.0
    assert result["phrases"][1]["relative_anchor"]["alignment_edge"] == "right"
    assert len(result["separator_candidates"]) == 3
    assert "classification" not in result
    assert "candidate_cells" not in result


def test_multiple_recurring_numeric_columns_remain_separate_measurements() -> None:
    tokens = []
    for row, y in enumerate((20, 40, 60)):
        tokens.extend([tok(f"Label{row}", [100, y, 180, y + 9], row), tok("1,000", [400, y, 440, y + 9], row), tok("2,000", [500, y, 560, y + 9], row)])
    result = derive_token_geometry(tokens, page_size=[600, 100])
    assert result["diagnostics"]["n_recurring_columns"] == 2
    assert [column["right_x"] for column in result["column_candidates"]] == [440, 560]


def test_shifted_by_ou_ps_anchor_is_found_relative_to_total() -> None:
    tokens = []
    for row, y in enumerate((20, 40, 60)):
        tokens.extend([
            tok(f"Label{row}", [80, y, 180, y + 9], row),
            tok("1,000", [345, y, 375, y + 9], row),
            tok("2,000", [415, y, 445, y + 9], row),
            tok("3,000", [555, y, 585, y + 9], row),
        ])
    result = derive_token_geometry(tokens, page_size=[720, 864])
    assert [column["right_x"] for column in result["column_candidates"]] == [375, 445, 585]
    assert result["diagnostics"]["provisional_total_right_x"] == 585
    assert result["diagnostics"]["column_search_left_x"] < 375


def test_band_clustering_does_not_single_link_drift_between_rows() -> None:
    tokens = [tok("left", [10, 10, 30, 20.0], 0), tok("middle", [40, 11, 70, 21.5], 0), tok("next", [10, 14, 30, 23.0], 1)]
    result = derive_token_geometry(tokens, page_size=[100, 100])
    assert len(result["baseline_bands"]) == 2


def test_marker_gap_compensates_for_inflated_punctuation_box() -> None:
    tokens = [
        tok("1", [181.08, 207.36, 182.52, 216], 18),
        tok(".", [185.4, 207.36, 192.6, 216], 18),
        tok("Preventive", [199.8, 207.36, 237.24, 216], 18),
    ]
    result = derive_token_geometry(tokens, page_size=[612.72, 792])
    marker_gap = result["gaps"][1]
    assert marker_gap["gap_pt"] == 7.2
    assert marker_gap["compensated_gap_pt"] > marker_gap["gap_pt"]
    assert marker_gap["marker_width_disagreement_pt"] > 0
    assert marker_gap["reason"] == "marker_compensated_gap"
    assert [phrase["text"] for phrase in result["phrases"]] == ["1.", "Preventive"]


def test_generic_phrase_split_requires_nine_physical_points() -> None:
    tokens = [
        tok("Alpha", [10, 10, 30, 19], 0),
        tok("Beta", [38, 10, 54, 19], 0),
    ]
    result = derive_token_geometry(tokens, page_size=[100, 100])
    assert result["gaps"][0]["gap_pt"] == 8
    assert result["gaps"][0]["split"] is False
    assert [phrase["text"] for phrase in result["phrases"]] == ["Alpha Beta"]


def test_program_code_is_split_from_following_label_and_not_money() -> None:
    tokens = [
        tok("100000000000000", [131.4, 20, 190.8, 29], 0),
        tok("General", [201.24, 20, 226.44, 29], 1),
        tok("Administration", [236.16, 20, 290.52, 29], 1),
    ]
    result = derive_token_geometry(tokens, page_size=[720, 864])
    assert [phrase["text"] for phrase in result["phrases"]] == [
        "100000000000000", "General Administration",
    ]
    assert [phrase["observation"] for phrase in result["phrases"]] == [
        "code_candidate", "text_candidate",
    ]
    assert result["gaps"][0]["reason"] == "program_code_boundary"
    assert result["gaps"][0]["estimated_spaces"] < 3
    assert all(0 not in indent["phrase_ids"] for indent in result["label_indent_anchors"])


def test_amount_aligned_label_is_main_and_unaligned_label_is_wrapped() -> None:
    tokens = []
    for row, y in enumerate((20, 40, 60)):
        tokens.extend([
            tok("Wrapped" if row == 0 else f"Main {row}", [100, y, 180, y + 9], row),
            *([] if row == 0 else [tok(f"{row},000,000", [500, y, 560, y + 9], row)]),
        ])
    result = derive_token_geometry(tokens, page_size=[600, 100])
    labels = [phrase for phrase in result["phrases"]
              if phrase["observation"] in {"text_candidate", "mixed_candidate"}]
    assert labels[0]["text_candidate_type"] == "wrapped_text_candidate"
    assert [phrase["text_candidate_type"] for phrase in labels[1:]] == [
        "main_text_candidate", "main_text_candidate",
    ]
    assert labels[1]["aligned_amount_phrase_ids"]


def test_detached_and_attached_currency_prefixes_split_amount_columns() -> None:
    tokens = [
        tok("TOTAL", [40, 20, 80, 29], 0),
        tok("P", [280, 20, 282, 29], 0), tok("14", [289, 20, 297, 29], 0),
        tok(",", [299, 20, 301, 29], 0), tok("922", [304, 20, 316, 29], 0),
        tok("P603", [324, 20, 340, 29], 0), tok(",", [343, 20, 345, 29], 0),
        tok("000", [348, 20, 360, 29], 0),
    ]
    result = derive_token_geometry(tokens, page_size=[400, 100])
    assert [phrase["text"] for phrase in result["phrases"]] == [
        "TOTAL", "P 14, 922", "P603, 000",
    ]
    assert [phrase["observation"] for phrase in result["phrases"]] == [
        "text_candidate", "money_candidate", "money_candidate",
    ]
    reasons = [gap["reason"] for gap in result["gaps"] if gap["split"]]
    assert reasons.count("currency_prefix_boundary") == 2


def test_sloped_amount_edges_merge_after_drift_correction() -> None:
    tokens = []
    for row, y in enumerate((100, 200, 300, 400, 500, 600, 700)):
        right = 600 + y * 0.015
        tokens.extend([
            tok(f"Label{row}", [100, y, 180, y + 9], row),
            tok(f"{row + 1},000,000", [right - 50, y, right, y + 9], row),
        ])
    result = derive_token_geometry(tokens, page_size=[720, 864])
    assert len(result["column_candidates"]) == 1
    column = result["column_candidates"][0]
    assert column["n_phrases"] == 7
    assert column["drift_slope_dx_dy"] == 0.015
    assert column["line_segment"][0] < column["line_segment"][2]


def test_single_amount_remains_a_provisional_column_anchor() -> None:
    tokens = [
        tok("Only row", [100, 100, 180, 109], 0),
        tok("12,345,000", [550, 100, 610, 109], 0),
    ]
    result = derive_token_geometry(tokens, page_size=[720, 864])
    column = result["column_candidates"][0]
    assert column["n_phrases"] == 1
    assert column["support"] == "singleton_amount_anchor"
    assert column["review"] is True
    assert result["phrases"][1]["right_edge_anchor"]["raw_x"] == 610
