from __future__ import annotations

from conftest import load_etl_node

merge_layers = load_etl_node("004.00-extract.py").merge_layers


def test_merge_is_paddle_first_and_model_layout_free() -> None:
    paddle = {
        "tokens": [{"text": "ACTIVITIES", "bbox": [10, 20, 50, 30], "line_id": 0}],
        "lines": [{"line_id": 0, "text": "ACTIVITIES", "bbox": [10, 20, 50, 30], "token_ids": [0]}],
        "stats": {"n_tokens": 1, "n_lines": 1, "mean_confidence": 0.99},
        "page_size_pt": [100, 200],
    }
    result = merge_layers(page_no=8, paddle=paddle, dpi=200)
    assert result["tokens"][0]["text"] == "ACTIVITIES"
    assert result["zones"][0]["token_ids"] == [0]
    assert result["zones"][0]["label"] == "page"
    assert result["regions"] == []
    assert result["tables"] == []
    assert result["extract_stats"]["model_layout_used"] is False
    assert result["extract_stats"]["model_cells_used"] is False
    assert "pdf_patch" not in result
    assert result["artifact"]["stage"] == "extract"
