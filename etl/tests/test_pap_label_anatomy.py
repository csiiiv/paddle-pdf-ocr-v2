from __future__ import annotations

import sys
from pathlib import Path

ETL = Path(__file__).resolve().parents[1]
if str(ETL) not in sys.path:
    sys.path.insert(0, str(ETL))

from _shared.pap_label_anatomy import (  # noqa: E402
    build_label_line_metrics,
    enrich_pap_label,
    split_title_description_geometry,
)


def test_maharlika_chainage_strip():
    raw = (
        "Maharlika Highway (LZ) • K0028+150 - K0031+420 • K0035+000 - K0038+200 • "
        "K0040+100 - K0042+500"
    )
    result = enrich_pap_label(raw)
    assert result["label"] == "Maharlika Highway (LZ)"
    assert result["label_ocr"] == raw
    assert len(result["chainages"]) == 3
    assert result["chainages"][0]["from"].startswith("0028")


def test_gps_strip_after_chainage():
    raw = "Construction of Pumping Station, Malabon City (14.672467, 120.942268)"
    result = enrich_pap_label(raw)
    assert "14.672467" not in result["label"]
    assert result["coordinates"][0]["lat"] == 14.672467
    assert result["coordinates"][0]["lon"] == 120.942268


def test_geometry_split_uses_run_gap_on_first_line():
    metrics = [
        {
            "text": "Asset Preservation Program",
            "fill": 0.24,
            "run_gap_pt": 321.48,
            "run_gap_spaces": 92.379,
            "trail_gap_pt": 317.0,
        },
        {
            "text": "The program aims to improve the quality of national roads.",
            "fill": 0.87,
            "run_gap_pt": 0.0,
            "run_gap_spaces": 0.0,
            "trail_gap_pt": 57.4,
        },
    ]
    title, description = split_title_description_geometry(metrics)
    assert title == "Asset Preservation Program"
    assert "program aims" in description


def test_geometry_split_long_title_with_the_prose():
    metrics = [
        {
            "text": "Rehabilitation / Reconstruction / Upgrading of Damaged Paved Roads",
            "fill": 0.66,
            "run_gap_pt": 140.0,
            "run_gap_spaces": 36.5,
            "trail_gap_pt": 139.0,
        },
        {
            "text": "The Rehabilitation, Reconstruction, and Upgrading of damaged paved roads.",
            "fill": 0.86,
            "run_gap_pt": 0.0,
            "run_gap_spaces": 0.0,
            "trail_gap_pt": 57.0,
        },
    ]
    title, description = split_title_description_geometry(metrics)
    assert title.startswith("Rehabilitation / Reconstruction")
    assert description.startswith("The Rehabilitation")


def test_geometry_split_rejects_wrapped_chainage():
    metrics = [
        {
            "text": "Maharlika Highway (LZ ) - K0028+150 - K0031+420",
            "fill": 0.88,
            "run_gap_pt": 64.8,
            "run_gap_spaces": 17.3,
            "trail_gap_pt": 38.5,
        },
        {
            "text": "K0035+000 - K0038+200",
            "fill": 0.34,
            "run_gap_pt": 0.0,
            "run_gap_spaces": 0.0,
            "trail_gap_pt": 217.0,
        },
    ]
    assert split_title_description_geometry(metrics) is None


def test_description_split_before_chainage():
    metrics = [
        {
            "text": "Asset Preservation Program",
            "fill": 0.24,
            "run_gap_pt": 321.48,
            "run_gap_spaces": 92.379,
            "trail_gap_pt": 317.0,
        },
        {
            "text": "The program aims to preserve national roads K0028+150 - K0031+420",
            "fill": 0.87,
            "run_gap_pt": 0.0,
            "run_gap_spaces": 0.0,
            "trail_gap_pt": 57.4,
        },
    ]
    raw = (
        "Asset Preservation Program\n"
        "The program aims to preserve national roads K0028+150 - K0031+420"
    )
    result = enrich_pap_label(raw, label_raw=raw, line_metrics=metrics)
    assert result["label"] == "Asset Preservation Program"
    assert "program aims" in result["description"]
    assert len(result["chainages"]) == 1


def test_build_label_line_metrics_from_cell_and_gaps():
    label_cell = {
        "bbox": [142.2, 150.7, 561.4, 231.6],
        "lines": [
            {"band_id": 4, "phrase_ids": [7], "text": "Asset Preservation Program"},
            {"band_id": 5, "phrase_ids": [9], "text": "The program aims to improve"},
        ],
    }
    phrases = {
        7: {"phrase_id": 7, "token_ids": [100, 101, 102],
            "bbox": [142.2, 153.0, 244.4, 161.3]},
        9: {"phrase_id": 9, "token_ids": [110, 111],
            "bbox": [141.1, 162.0, 504.0, 170.0]},
    }
    gaps = [
        {"band_id": 4, "left_token_id": 102, "right_token_id": 200,
         "gap_pt": 321.48, "estimated_spaces": 92.379},
        {"band_id": 5, "left_token_id": 110, "right_token_id": 111,
         "gap_pt": 5.4, "estimated_spaces": 1.9},
    ]
    metrics = build_label_line_metrics(label_cell, phrases, gaps)
    assert metrics is not None
    assert metrics[0]["run_gap_pt"] == 321.48
    assert metrics[0]["fill"] < 0.3
