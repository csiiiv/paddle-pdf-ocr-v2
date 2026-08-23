from __future__ import annotations

import tempfile
from datetime import datetime
from pathlib import Path

import pytest
import pymupdf

from _common import PROJECT, StageContext, resolve_pdf
from _shared.artifacts import ArtifactStore, read_json, write_json_atomic
from _shared.contracts import ContractError, stamp_meta, validate_extract
from _shared.raster import render_page_rgb
from _shared.timestamps import iso_now
from conftest import load_etl_node

PADDLE_NODE = load_etl_node("001.00-paddle-ocr.py")
LAYOUT_NODE = load_etl_node("002.00-layout.py")
EXTRACT_NODE = load_etl_node("004.00-extract.py")


def _context(pdf: Path, run_dir: Path, pages: list[int]) -> StageContext:
    return StageContext(pdf=pdf, run_dir=run_dir, pages=pages, dpi=200,
                        device="gpu:0", layout_score=0.4, cells_score=0.3)


def _assert_captured_timing(record: dict) -> None:
    started = datetime.fromisoformat(record["started_at"])
    completed = datetime.fromisoformat(record["completed_at"])
    assert started.tzinfo is not None
    assert completed.tzinfo is not None
    assert started.microsecond == completed.microsecond == 0
    assert started <= completed
    assert record["timestamp_source"] == "captured"
    assert record["elapsed_s"] >= 0


def test_iso_timestamp_has_timezone_and_second_precision() -> None:
    value = datetime.fromisoformat(iso_now())
    assert value.tzinfo is not None
    assert value.microsecond == 0


def test_relative_pdf_resolution_prefers_project_local_file() -> None:
    resolved = resolve_pdf(Path("pdfs/NEP-2027-VOLUME-2B_OCR.pdf"))
    assert resolved == PROJECT / "pdfs/NEP-2027-VOLUME-2B_OCR.pdf"


def test_extract_contract() -> None:
    validate_extract(
        {"page": 1, "tokens": [], "lines": [], "regions": [], "zones": []}
    )
    with pytest.raises(ContractError):
        validate_extract({"page": 1, "tokens": [], "lines": []})


def test_artifact_stamp_is_explicit() -> None:
    data = stamp_meta({}, stage="extract", producer="hybrid_v2")
    assert data["artifact"] == {
        "version": 1,
        "stage": "extract",
        "producer": "hybrid_v2",
    }


def test_atomic_json_roundtrip_and_discovery() -> None:
    with tempfile.TemporaryDirectory() as td:
        store = ArtifactStore(Path(td))
        write_json_atomic(store.extract_path(12), {"page": 12})
        write_json_atomic(store.extract_path(3), {"page": 3})
        assert store.discover_pages() == [3, 12]
        assert read_json(store.extract_path(3))["page"] == 3
        assert list(store.extract_path(3).parent.glob("*.tmp")) == []


def test_qa_name_cannot_escape_run() -> None:
    with pytest.raises(ValueError):
        ArtifactStore(Path("run")).stage_qa_path("paddle", "../outside.json")


def test_rows_and_final_structure_have_distinct_owners() -> None:
    store = ArtifactStore(Path("run"))
    assert store.rows_path(7) == Path("run/006.00-rows/pages/page-0007.json")
    assert store.structured_path(7) == Path("run/008.00-hierarchy/pages/page-0007.json")


def test_numbered_stage_paths_make_order_and_qa_ownership_explicit() -> None:
    store = ArtifactStore(Path("run"))
    assert store.layer_path("paddle", 7) == Path("run/001.00-paddle-ocr/pages/page-0007.json")
    assert store.layer_path("layout", 7) == Path("run/002.00-layout/pages/page-0007.json")
    assert store.layer_path("cells", 7) == Path("run/003.00-table-cells/pages/page-0007.json")
    assert store.extract_path(7) == Path("run/004.00-extract/pages/page-0007.json")
    assert store.stage_qa_path("layout") == Path("run/002.00-layout/qa/summary.json")
    assert store.stage_qa_path("foundation", "tests.json") == Path("run/000.00-foundation/qa/tests.json")


def _sample_pdf(path: Path) -> None:
    document = pymupdf.open()
    page = document.new_page(width=300, height=200)
    page.insert_text((30, 40), "National Capital Region")
    page.insert_text((30, 70), "Budget 123,456")
    document.save(path)
    document.close()


def test_raster_contract() -> None:
    with tempfile.TemporaryDirectory() as td:
        pdf = Path(td) / "sample.pdf"
        _sample_pdf(pdf)
        with pymupdf.open(pdf) as document:
            page = document[0]
            image, size = render_page_rgb(page, dpi=144)
            assert image.shape == (400, 600, 3)
            assert size == (300.0, 200.0)


def test_pipeline_writes_canonical_paddle_layer_and_qa() -> None:
    class Engine:
        def predict(self, image, *, return_word_box: bool):
            assert return_word_box is True
            return [
                {
                    "rec_texts": ["Budget 123,456"],
                    "rec_scores": [0.99],
                    "dt_polys": [[10, 10, 200, 40]],
                }
            ]

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        pdf = root / "sample.pdf"
        run_dir = root / "run"
        _sample_pdf(pdf)
        context = _context(pdf, run_dir, [1])
        summary = PADDLE_NODE.run_stage(context, engine=Engine())

        layer = read_json(run_dir / "001.00-paddle-ocr/pages/page-0001.json")
        assert layer["artifact"]["stage"] == "layer:paddle"
        assert layer["tokens"][0]["source"] == "paddle"
        assert layer["image_size_px"] == [834, 556]
        assert summary["canonical"] is True
        _assert_captured_timing(summary)
        _assert_captured_timing(summary["pages"][0])
        assert read_json(run_dir / "001.00-paddle-ocr/qa/summary.json")["pass"] is True


def test_pipeline_writes_layout_layer_and_qa() -> None:
    class Engine:
        def predict(self, image):
            return [{"boxes": [{
                "label": "table", "score": 0.95,
                "coordinate": [10, 20, 200, 300],
            }]}]

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        pdf = root / "sample.pdf"
        run_dir = root / "run"
        _sample_pdf(pdf)
        context = _context(pdf, run_dir, [1])
        summary = LAYOUT_NODE.run_stage(context, engine=Engine())
        layer = read_json(run_dir / "002.00-layout/pages/page-0001.json")
        assert layer["artifact"]["stage"] == "layer:layout"
        assert layer["regions"][0]["label"] == "table"
        assert summary["pages"][0]["n_table"] == 1
        _assert_captured_timing(summary)
        _assert_captured_timing(summary["pages"][0])
        assert read_json(run_dir / "002.00-layout/qa/summary.json")["pass"] is True


def test_assemble_requires_no_pdf_text_layer() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        pdf = root / "sample.pdf"
        run_dir = root / "run"
        _sample_pdf(pdf)
        store = ArtifactStore(run_dir)
        write_json_atomic(store.layer_path("paddle", 1), {
            "page": 1,
            "tokens": [{"text": "Budget", "bbox": [10, 10, 30, 20], "line_id": 0}],
            "lines": [{"line_id": 0, "text": "Budget", "bbox": [10, 10, 30, 20], "token_ids": [0]}],
            "stats": {"n_tokens": 1, "n_lines": 1, "mean_confidence": 0.99},
            "page_size_pt": [300, 200],
        })
        write_json_atomic(store.layer_path("layout", 1), {
            "page": 1,
            "regions": [{"region_id": 0, "label": "text", "bbox": [0, 0, 100, 100], "score": 0.9, "chrome": False}],
            "stats": {"n_regions": 1, "n_chrome": 0, "n_table": 0, "n_text": 1},
        })
        summary = EXTRACT_NODE.run_stage(_context(pdf, run_dir, [1]))
        assert summary["pass"] is True
        _assert_captured_timing(summary)
        _assert_captured_timing(summary["pages"][0])
        assert not (run_dir / "layers").exists()
        extract = read_json(store.extract_path(1))
        assert extract["source_mode"] == "paddle_geometry_primary"
        assert extract["regions"] == []
        assert extract["tables"] == []
        assert extract["extract_stats"]["model_layout_used"] is False
        assert "pdf_patch" not in extract
