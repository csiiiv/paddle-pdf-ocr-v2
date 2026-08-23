from __future__ import annotations

import numpy as np

from conftest import load_etl_node

node = load_etl_node("003.00-table-cells.py")
_clusters, detect_cells, parse_cell_result = node._clusters, node.detect_cells, node.parse_cell_result


def test_clusters_preserve_single_link_drift() -> None:
    assert len(_clusters([0, 15, 30], 18)) == 1


def test_cell_parser_handles_threshold_and_numpy_boxes() -> None:
    result = parse_cell_result([{"boxes": [
        {"score": 0.8, "coordinate": np.array([1, 2, 10, 20])},
        {"score": 0.1, "coordinate": [2, 3, 4, 5]},
    ]}], score_thresh=0.3)
    assert result == [([1.0, 2.0, 10.0, 20.0], 0.8)]


def test_detect_cells_assigns_grid_and_line_text() -> None:
    class Engine:
        def predict(self, crop):
            assert crop.shape[2] == 3
            boxes = []
            for row in range(3):
                for col in range(2):
                    boxes.append({
                        "score": 0.9,
                        "coordinate": [col * 100, row * 50, (col + 1) * 100, (row + 1) * 50],
                    })
            return [{"boxes": boxes}]

    regions = [{"region_id": 0, "label": "table", "bbox": [4, 4, 76, 58], "chrome": False}]
    tokens = [{"text": "Budget", "bbox": [10, 10, 30, 20], "line_id": 0, "chrome": False}]
    lines = [{"line_id": 0, "text": "Budget", "bbox": [10, 10, 30, 20], "token_ids": [0], "chrome": False}]
    result = detect_cells(
        np.zeros((200, 300, 3), dtype=np.uint8), dpi=100,
        regions=regions, tokens=tokens, lines=lines, wired_engine=Engine(),
    )
    table = result["tables"][0]
    assert table["ok"] is True
    assert (table["n_rows"], table["n_cols"]) == (3, 2)
    assert table["cells"][0]["text"] == "Budget"
    assert result["stats"] == {"n_tables": 1, "n_cells": 6, "n_ok": 1, "n_weak": 0}


def test_cells_skip_non_table_regions() -> None:
    result = detect_cells(
        np.zeros((20, 20, 3), dtype=np.uint8), dpi=200,
        regions=[{"region_id": 0, "label": "text", "bbox": [0, 0, 10, 10]}],
        tokens=[], lines=[], wired_engine=object(),
    )
    assert result["tables"] == []
    assert result["stats"]["n_tables"] == 0
