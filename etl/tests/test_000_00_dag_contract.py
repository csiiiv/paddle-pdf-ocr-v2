from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from conftest import load_etl_node


PROJECT = Path(__file__).resolve().parents[2]
ETL = PROJECT / "etl"
ORCHESTRATOR = load_etl_node("run_etl.py")


def test_implemented_etl_scripts_mirror_numbered_stages() -> None:
    scripts = sorted(path.name for path in ETL.glob("[0-9]*.py"))
    assert scripts == [
        "000.00-foundation.py",
        "001.00-paddle-ocr.py",
        "002.00-layout.py",
        "002.10-token-geometry.py",
        "003.00-table-cells.py",
        "004.00-extract.py",
        "005.00-schema.py",
    ]


def test_each_etl_stage_has_an_executable_help_contract() -> None:
    for script in sorted(ETL.glob("[0-9]*.py")):
        result = subprocess.run(
            [sys.executable, str(script), "--help"],
            cwd=PROJECT,
            text=True,
            capture_output=True,
            check=False,
        )
        assert result.returncode == 0, (script.name, result.stderr)
        assert "Inputs:" in result.stdout
        assert "Outputs:" in result.stdout


def test_numbered_nodes_own_transformations_without_src_package() -> None:
    assert not (PROJECT / "src").exists()
    for script in sorted(ETL.glob("[0-9]*.py")):
        source = script.read_text(encoding="utf-8")
        if script.name != "000.00-foundation.py":
            assert "def run_stage(" in source, script.name
        assert "paddle_pdf_ocr_v2.pipeline" not in source
        assert "paddle_pdf_ocr_v2.extract" not in source


def test_numbered_nodes_do_not_import_each_other() -> None:
    names = [path.name for path in ETL.glob("[0-9]*.py")]
    for script in ETL.glob("[0-9]*.py"):
        source = script.read_text(encoding="utf-8")
        for other in names:
            if other != script.name:
                assert other not in source, (script.name, other)


def test_tests_are_visibly_numbered_by_dag_owner() -> None:
    tests = sorted(path.name for path in (ETL / "tests").glob("test_*.py"))
    assert all(name.startswith("test_00") for name in tests)
    for prefix in ("test_000_00_", "test_001_00_", "test_002_00_", "test_002_10_", "test_003_00_", "test_004_00_", "test_005_00_"):
        assert any(name.startswith(prefix) for name in tests), prefix


def test_shared_modules_have_multiple_numbered_consumers() -> None:
    expected_consumers = {
        "artifacts": {"001", "002", "003", "004", "005"},
        "contracts": {"001", "002", "003", "004", "005"},
        "manifest": {"001", "002", "003", "004", "005"},  # through _common
        "raster": {"001", "002", "003"},
        "regions": {"002", "003", "004"},
        "timestamps": {"000", "001", "002", "003", "004", "005"},
    }
    modules = {path.stem for path in (ETL / "_shared").glob("*.py")
               if path.stem != "__init__"}
    assert modules == set(expected_consumers)
    assert all(len(consumers) >= 2 for consumers in expected_consumers.values())


def test_canonical_dag_document_covers_registered_nodes() -> None:
    document = (PROJECT / "docs" / "ETL_DAG.md").read_text(encoding="utf-8")
    for directory in (
        "000.00-foundation", "001.00-paddle-ocr", "002.00-layout",
        "002.10-token-geometry",
        "003.00-table-cells", "004.00-extract", "005.00-schema",
        "006.00-rows", "007.00-domain", "008.00-hierarchy",
        "009.00-collation", "999.00-run-qa",
    ):
        assert directory in document
    assert "HUMAN_OVERRIDES.md" in document
    assert "ISS-012" in document and "ISS-015" in document


def test_orchestrator_selects_inclusive_ordered_major_range() -> None:
    selected = ORCHESTRATOR.select_stages(
        ORCHESTRATOR.stage_bound("1", end=False),
        ORCHESTRATOR.stage_bound("3", end=True),
    )
    assert [stage.name for stage in selected] == [
        "001.00-paddle-ocr", "002.10-token-geometry",
    ]


def test_orchestrator_expands_multiple_one_based_ranges() -> None:
    assert ORCHESTRATOR.parse_pages("1-2,3,5-7") == [1, 2, 3, 5, 6, 7]


def test_orchestrator_rejects_page_zero() -> None:
    with pytest.raises(ValueError, match="invalid page selection"):
        ORCHESTRATOR.parse_pages("0-1,2")


def test_orchestrator_includes_active_insertions_in_major_range(monkeypatch) -> None:
    insertion = ORCHESTRATOR.ActiveStage(2, 20, "002.20-example.py")
    monkeypatch.setattr(
        ORCHESTRATOR, "ACTIVE_STAGES",
        tuple(sorted((*ORCHESTRATOR.ACTIVE_STAGES, insertion), key=lambda stage: stage.key)),
    )
    selected = ORCHESTRATOR.select_stages((2, 0), (2, 99))
    assert [stage.name for stage in selected] == [
        "002.10-token-geometry", "002.20-example",
    ]


def test_orchestrator_rejects_descending_stage_range() -> None:
    with pytest.raises(ValueError, match="precedes"):
        ORCHESTRATOR.select_stages((4, 0), (2, 99))


def test_orchestrator_dry_run_has_no_output_side_effect() -> None:
    run = "unit-dry-run-must-not-exist"
    result = subprocess.run(
        [sys.executable, str(ETL / "run_etl.py"),
         "--pdf-source", "pdfs/NEP-2027-VOLUME-2B_OCR.pdf",
         "--pages", "1-2,3,5-7", "--start-stage", "1",
         "--end-stage", "3", "--run", run, "--dry-run"],
        cwd=PROJECT, text=True, capture_output=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "Pages (1-based): 1,2,3,5,6,7" in result.stdout
    assert "001.00-paddle-ocr" in result.stdout
    assert "002.10-token-geometry" in result.stdout
    assert "003.00-table-cells" not in result.stdout
    assert "004.00-extract" not in result.stdout
    assert not (PROJECT / "output" / run).exists()


def test_orchestrator_defaults_to_page_one_and_full_active_sequence() -> None:
    run = "unit-default-dry-run-must-not-exist"
    result = subprocess.run(
        [sys.executable, str(ETL / "run_etl.py"),
         "--pdf-source", "pdfs/NEP-2027-VOLUME-2B_OCR.pdf",
         "--run", run, "--dry-run"],
        cwd=PROJECT, text=True, capture_output=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "Pages (1-based): 1" in result.stdout
    for stage in ORCHESTRATOR.ACTIVE_STAGES:
        assert stage.name in result.stdout
    assert not (PROJECT / "output" / run).exists()


def test_orchestrator_default_run_name_is_pdf_stem() -> None:
    pdf = PROJECT / "pdfs" / "NEP-2027-VOLUME-2B_OCR.pdf"
    assert ORCHESTRATOR.default_run_name(pdf) == "NEP-2027-VOLUME-2B_OCR"
    result = subprocess.run(
        [sys.executable, str(ETL / "run_etl.py"),
         "--pdf-source", "pdfs/NEP-2027-VOLUME-2B_OCR.pdf", "--dry-run"],
        cwd=PROJECT, text=True, capture_output=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "ETL run: NEP-2027-VOLUME-2B_OCR" in result.stdout
    assert "-etl-" not in result.stdout.splitlines()[0]


def test_orchestrator_pages_json_overrides_pages_arg() -> None:
    run = "unit-pages-json-dry-run-must-not-exist"
    result = subprocess.run(
        [sys.executable, str(ETL / "run_etl.py"),
         "--pdf-source", "pdfs/NEP-2027-VOLUME-2B_OCR.pdf",
         "--pages", "1",
         "--pages-json", "fixtures/migration_gold.json",
         "--pages-obj", "edge_pages",
         "--run", run, "--dry-run"],
        cwd=PROJECT, text=True, capture_output=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "overrides --pages='1'" in result.stdout
    assert "Pages (1-based): 8,11,13," in result.stdout
    assert "247" in result.stdout
    assert not (PROJECT / "output" / run).exists()


def test_orchestrator_pages_json_requires_pages_obj() -> None:
    result = subprocess.run(
        [sys.executable, str(ETL / "run_etl.py"),
         "--pdf-source", "pdfs/NEP-2027-VOLUME-2B_OCR.pdf",
         "--pages-json", "fixtures/migration_gold.json",
         "--dry-run"],
        cwd=PROJECT, text=True, capture_output=True, check=False,
    )
    assert result.returncode != 0
    assert "must be used together" in (result.stderr + result.stdout)
