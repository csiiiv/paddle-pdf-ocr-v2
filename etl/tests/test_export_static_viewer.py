from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
SCRIPTS = PROJECT / "scripts"


def load_export_module():
    path = SCRIPTS / "export_static_viewer.py"
    module_name = "export_static_viewer_test"
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def test_slim_node_by_ou_format_2():
    export = load_export_module()
    raw = {
        "id": "p28:r8",
        "kind": "program",
        "tier": 1,
        "label": "ASSET PRESERVATION PROGRAM",
        "code": "310101100238000",
        "page": 28,
        "parent_pdf": "p13:ph13",
        "parent_prexc": "p28:r7",
        "bbox": [1, 2, 3, 4],
        "amounts": {"Total": {"text": "100", "value": 100}},
        "total": None,
    }
    slim = export.slim_node(raw, {}, dual_hierarchy=True, row_index=42)
    assert slim["row_index"] == 42
    assert slim["tier_pdf"] == 1
    assert slim["parent_pdf"] == "p13:ph13"
    assert slim["parent_prexc"] == "p28:r7"
    assert "parent" not in slim
    assert slim["prexc"]["identifier"] == "1"


def test_csv_row_by_ou_includes_hierarchy_columns():
    export = load_export_module()
    node = {
        "row_index": 1,
        "id": "p28:r8",
        "kind": "program",
        "page": 28,
        "tier_pdf": 1,
        "label": "ASSET PRESERVATION PROGRAM",
        "code": "310100000000000",
        "parent_pdf": "p13:ph13",
        "parent_prexc": "p28:r7",
        "prexc": {"identifier": "1"},
        "amounts": {"Total": {"text": "100", "value": 100}},
        "total": None,
    }
    depth_pdf = export.compute_depths([node, {
        "id": "p13:ph13", "parent_pdf": None, "parent_prexc": None,
    }], "parent_pdf")
    row = export.csv_row_values(node, "by-ou", depth_pdf, {"p28:r8": 2})
    assert row["parent_id_pdf"] == "p13:ph13"
    assert row["parent_id_prexc"] == "p28:r7"
    assert row["prexc_identifier"] == "1"
    assert row["total"] == 100
    assert export.DATA_SPECS["by-ou"]["columns"][0] == "row_index"


def test_validate_tree_rejects_ambiguous_parent_on_dual():
    export = load_export_module()
    slim = {
        "format": 2,
        "roots": ["root"],
        "hierarchy_modes": ["pdf", "prexc"],
        "nodes": [
            {
                "row_index": 0,
                "id": "root",
                "kind": "table_root",
                "tier_pdf": 0,
                "parent_pdf": None,
                "parent_prexc": None,
                "bbox": None,
                "page": None,
            },
            {
                "row_index": 1,
                "id": "n1",
                "kind": "program",
                "tier_pdf": 1,
                "parent": "root",
                "parent_pdf": "root",
                "parent_prexc": "root",
                "bbox": [1, 2, 3, 4],
                "page": 13,
            },
        ],
    }
    try:
        export.validate_tree(slim, Path("test.json"))
        raise AssertionError("expected validation failure")
    except ValueError as exc:
        assert "must not carry parent" in str(exc)


def test_copy_pdf_to_pack_linearizes(tmp_path):
    import pikepdf

    export = load_export_module()
    source = tmp_path / "src.pdf"
    target = tmp_path / "out.pdf"
    pdf = pikepdf.Pdf.new()
    pdf.add_blank_page(page_size=(612, 792))
    pdf.save(source)
    assert not export.pdf_looks_linearized(source)

    assert export.copy_pdf_to_pack(source, target, linearize=True) is True
    assert target.is_file()
    assert export.pdf_looks_linearized(target)

    plain = tmp_path / "plain.pdf"
    assert export.copy_pdf_to_pack(source, plain, linearize=False) is False
    assert plain.is_file()
    assert not export.pdf_looks_linearized(plain)
