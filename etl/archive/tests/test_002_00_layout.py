from __future__ import annotations

import numpy as np

from conftest import load_etl_node

node = load_etl_node("002.00-layout.py")
assign_regions = node.assign_regions
extract_layout = node.extract_layout
parse_layout_result = node.parse_layout_result


def test_layout_parser_filters_scales_and_orders_regions() -> None:
    result = parse_layout_result(
        [{"boxes": [
            {"label": "table", "score": 0.95, "coordinate": [20, 100, 200, 300]},
            {"label": "header", "score": 0.8, "coordinate": [10, 10, 210, 50]},
            {"label": "text", "score": 0.2, "coordinate": [10, 60, 100, 90]},
            {"label": "broken", "score": 0.9, "coordinate": [1, 2, 3]},
        ]}],
        dpi=144,
    )
    assert [region["label"] for region in result["regions"]] == ["header", "table"]
    assert result["regions"][0]["bbox"] == [5.0, 5.0, 105.0, 25.0]
    assert result["regions"][0]["chrome"] is True
    assert result["stats"] == {"n_regions": 2, "n_chrome": 1, "n_table": 1, "n_text": 0}
    assert result["diagnostics"]["n_below_threshold"] == 1
    assert result["diagnostics"]["n_invalid_boxes"] == 1


def test_assignment_prefers_table_and_builds_nonchrome_zone() -> None:
    regions = [
        {"region_id": 0, "label": "header", "bbox": [0, 0, 100, 20], "score": 0.9, "chrome": True},
        {"region_id": 1, "label": "text", "bbox": [0, 20, 100, 100], "score": 0.8, "chrome": False},
        {"region_id": 2, "label": "table", "bbox": [0, 20, 100, 100], "score": 0.9, "chrome": False},
    ]
    tokens = [
        {"text": "page", "bbox": [10, 5, 30, 15], "line_id": 0},
        {"text": "amount", "bbox": [10, 30, 40, 40], "line_id": 1},
        {"text": "outside", "bbox": [110, 30, 140, 40], "line_id": 2},
    ]
    lines = [
        {"line_id": 0, "bbox": [10, 5, 30, 15], "token_ids": [0]},
        {"line_id": 1, "bbox": [10, 30, 40, 40], "token_ids": [1]},
        {"line_id": 2, "bbox": [110, 30, 140, 40], "token_ids": [2]},
    ]
    result = assign_regions(tokens, lines, regions)
    assert tokens[0]["chrome"] is True
    assert tokens[1]["region_id"] == 2
    assert tokens[2]["region_id"] is None
    assert result["n_chrome_tokens"] == 1
    assert result["n_unassigned_tokens"] == 1
    assert [zone["region_id"] for zone in result["zones"]] == [1, 2]
    assert result["zones"][1]["token_ids"] == [1]


def test_layout_engine_receives_bgr() -> None:
    class Engine:
        def predict(self, image: np.ndarray):
            assert image.tolist() == [[[30, 20, 10]]]
            return [{"boxes": []}]

    result = extract_layout(
        np.array([[[10, 20, 30]]], dtype=np.uint8), dpi=200, engine=Engine()
    )
    assert result["stats"]["n_regions"] == 0
