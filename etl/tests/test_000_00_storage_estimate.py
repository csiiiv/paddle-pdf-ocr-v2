from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from conftest import load_etl_node


PROJECT = Path(__file__).resolve().parents[2]
ETL = PROJECT / "etl"
STORAGE = load_etl_node("storage_estimate.py")


def test_page_count_scales_output_storage() -> None:
    stages = ["001.00-paddle-ocr", "002.00-layout", "003.00-table-cells", "004.00-extract"]
    one = STORAGE.estimate_run_storage(
        pages=[13], stages=stages, output_root=PROJECT / "output",
        free_bytes=10 * 1024 ** 3,
    )
    many = STORAGE.estimate_run_storage(
        pages=[8, 13, 115, 195, 247, 680], stages=stages,
        output_root=PROJECT / "output", free_bytes=10 * 1024 ** 3,
    )
    assert many.n_pages == 6
    assert many.estimated_bytes > one.estimated_bytes
    assert many.bytes_per_page == one.bytes_per_page
    assert many.estimated_bytes == (
        one.bytes_per_page * 6
        + sum(STORAGE.STAGE_FIXED_BYTES[s] for s in stages)
        + STORAGE.RUN_FIXED_BYTES
        + STORAGE.RUN_QA_BYTES
    )
    assert one.ok_to_run and many.ok_to_run


def test_storage_refuses_when_free_disk_too_low() -> None:
    estimate = STORAGE.estimate_run_storage(
        pages=list(range(1, 501)),
        stages=["001.00-paddle-ocr", "004.00-extract"],
        output_root=PROJECT / "output",
        free_bytes=1024,  # 1 KiB free
    )
    assert estimate.fits is False
    assert estimate.ok_to_run is False


def test_orchestrator_dry_run_prints_storage_estimate() -> None:
    run = "unit-storage-dry-run-must-not-exist"
    result = subprocess.run(
        [sys.executable, str(ETL / "run_etl.py"),
         "--pdf-source", "pdfs/NEP-2027-VOLUME-2B_OCR.pdf",
         "--pages", "8,13", "--run", run, "--dry-run"],
        cwd=PROJECT, text=True, capture_output=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "Storage estimate" in result.stdout
    assert "Run total:" in result.stdout
    assert "001.00-paddle-ocr:" in result.stdout
    assert not (PROJECT / "output" / run).exists()
