from __future__ import annotations

from conftest import load_etl_node

merge_layers = load_etl_node("004.00-extract.py").merge_layers


def test_merge_is_paddle_first_and_assigns_layout() -> None:
    paddle = {
        "tokens": [{"text": "ACTIVITIES", "bbox": [10, 20, 50, 30], "line_id": 0}],
        "lines": [{"line_id": 0, "text": "ACTIVITIES", "bbox": [10, 20, 50, 30], "token_ids": [0]}],
        "stats": {"n_tokens": 1, "n_lines": 1, "mean_confidence": 0.99},
        "page_size_pt": [100, 200],
    }
    layout = {
        "regions": [{"region_id": 0, "label": "table", "bbox": [0, 10, 90, 100], "score": 0.9, "chrome": False}],
        "stats": {"n_regions": 1, "n_table": 1, "n_chrome": 0, "n_text": 0},
    }
    result = merge_layers(page_no=8, paddle=paddle, layout=layout, dpi=200)
    assert result["tokens"][0]["text"] == "ACTIVITIES"
    assert result["tokens"][0]["region_id"] == 0
    assert result["zones"][0]["token_ids"] == [0]
    assert "pdf_patch" not in result
    assert result["artifact"]["stage"] == "extract"
