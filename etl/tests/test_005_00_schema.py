from __future__ import annotations

import pytest

from conftest import load_etl_node


NODE = load_etl_node("005.00-schema.py")


def extract_with_table(*, page: int = 13, cells: list[dict] | None = None) -> dict:
    zone = {"zone_id": 0, "region_id": 7, "label": "table", "token_ids": [], "line_ids": []}
    return {
        "page": page, "dpi": 200.0, "page_size_pt": [720, 864],
        "tokens": [], "lines": [], "regions": [], "zones": [zone],
        "tables": [{"table_id": 0, "region_id": 7, "cells": cells or []}],
    }


def cell(row: int, col: int, text: str, x: float) -> dict:
    return {"row": row, "col": col, "text": text, "bbox": [x, row * 20, x + 60, row * 20 + 18], "score": 0.9}


def test_lattice_roles_are_observed_from_headers() -> None:
    cells = [
        cell(0, 1, "Personnel Services", 300), cell(0, 2, "MOOE", 380),
        cell(0, 3, "Capital Outlays", 460), cell(0, 4, "Total", 540),
        cell(1, 0, "Program", 100), cell(1, 1, "1,000", 300),
        cell(1, 2, "2,000", 380), cell(1, 3, "3,000", 460), cell(1, 4, "6,000", 540),
    ]
    schema = NODE.infer_page_schema(extract_with_table(cells=cells))
    assert schema["schema_mode"] == "lattice"
    assert schema["col_roles"] == ["PS", "MOOE", "CO", "Total"]
    assert schema["qa_status"] == "accept"


def test_amount_php_header_selects_amount_anchored() -> None:
    cells = [cell(0, 1, "Amount (Php)", 500), cell(1, 0, "Project", 100), cell(1, 1, "12,500,000", 500)]
    schema = NODE.infer_page_schema(extract_with_table(page=115, cells=cells))
    assert schema["schema_mode"] == "amount_anchored"
    assert schema["col_roles"] == ["Amount"]
    assert "amount_php_header" in schema["zone_schemas"][0]["reasons"]


def test_years_are_not_misclassified_as_money() -> None:
    assert not NODE.is_money("2027")
    assert NODE.is_money("2,027,000")


def test_carry_is_only_allowed_on_contiguous_pages() -> None:
    ambiguous = extract_with_table(page=14)
    carry = {"schema_mode": "lattice", "col_roles": ["PS", "MOOE", "CO", "Total"], "col_centers": [300, 380, 460, 540]}
    contiguous = NODE.infer_page_schema(ambiguous, carry=carry, previous_page=13)
    sparse = NODE.infer_page_schema(ambiguous, carry=carry, previous_page=8)
    assert contiguous["schema_mode"] == "lattice"
    assert contiguous["sequence"]["carry_used"] is True
    assert sparse["schema_mode"] == "passthrough"
    assert sparse["sequence"]["carry_used"] is False


def test_amount_unit_carries_only_to_the_next_page() -> None:
    extract = extract_with_table(page=109, cells=[cell(0, 0, "Expense", 100), cell(0, 1, "1,000", 500)])
    carry = {"schema_mode": "years", "col_roles": [], "col_centers": [], "amount_unit": "thousand_pesos"}
    contiguous = NODE.infer_page_schema(extract, carry=carry, previous_page=108)
    sparse = NODE.infer_page_schema(extract, carry=carry, previous_page=107)
    assert contiguous["amount_unit"] == "thousand_pesos"
    assert "contiguous_unit_carry" in contiguous["zone_schemas"][0]["reasons"]
    assert sparse["amount_unit"] == "pesos"


def test_schema_contract_rejects_unknown_mode() -> None:
    schema = NODE.infer_page_schema(extract_with_table())
    schema["schema_mode"] = "guess"
    with pytest.raises(ValueError, match="schema_mode"):
        NODE.validate_schema(schema)
