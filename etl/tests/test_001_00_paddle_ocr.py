from __future__ import annotations

import numpy as np

from conftest import load_etl_node

node = load_etl_node("001.00-paddle-ocr.py")
parse_ocr_result, run_ocr = node.parse_ocr_result, node.run_ocr


def test_parse_word_boxes_in_pdf_coordinates() -> None:
    raw = {
        "rec_texts": ["ACTIVITIES 12,345"],
        "rec_scores": np.array([0.875]),
        "dt_polys": np.array([[[100, 200], [500, 200], [500, 240], [100, 240]]]),
        "text_word": [["ACTIVITIES", "12,345"]],
        "text_word_boxes": [
            [[100, 200, 300, 240], [320, 200, 500, 240]],
        ],
    }

    result = parse_ocr_result([raw], dpi=200)

    assert [token["text"] for token in result["tokens"]] == [
        "ACTIVITIES",
        "12,345",
    ]
    assert result["tokens"][0]["bbox"] == [36.0, 72.0, 108.0, 86.4]
    assert result["lines"][0]["bbox"] == [36.0, 72.0, 180.0, 86.4]
    assert result["lines"][0]["token_ids"] == [0, 1]
    assert result["stats"] == {
        "n_tokens": 2,
        "n_lines": 1,
        "mean_confidence": 0.875,
    }
    assert result["diagnostics"]["word_boxes_used"] is True


def test_parse_falls_back_to_one_token_per_line() -> None:
    result = parse_ocr_result(
        {
            "rec_texts": ["National Capital Region"],
            "rec_scores": [0.9],
            "dt_polys": [[[10, 20], [110, 20], [110, 40], [10, 40]]],
        },
        dpi=100,
    )

    assert [token["text"] for token in result["tokens"]] == [
        "National Capital Region"
    ]
    assert result["tokens"][0]["bbox"] == [7.2, 14.4, 79.2, 28.8]
    assert result["diagnostics"]["word_boxes_used"] is False


def test_nested_payload_offsets_lines_and_tokens_stably() -> None:
    page = {
        "res": [
            {
                "rec_texts": ["first", "second"],
                "rec_scores": [1.0, 1.0],
                "dt_polys": [[0, 0, 10, 10], [0, 20, 10, 30]],
            }
        ]
    }
    result = parse_ocr_result([page, page], dpi=72)

    assert [line["line_id"] for line in result["lines"]] == [0, 1, 2, 3]
    assert [token["line_id"] for token in result["tokens"]] == [0, 1, 2, 3]
    assert [line["token_ids"] for line in result["lines"]] == [[0], [1], [2], [3]]


def test_run_ocr_converts_rgb_to_bgr() -> None:
    class Engine:
        def predict(self, image: np.ndarray, *, return_word_box: bool,
                    text_det_box_thresh: float) -> list[dict]:
            assert return_word_box is True
            assert text_det_box_thresh == 0.55
            assert image.tolist() == [[[30, 20, 10]]]
            return []

    assert run_ocr(Engine(), np.array([[[10, 20, 30]]], dtype=np.uint8)) == []
