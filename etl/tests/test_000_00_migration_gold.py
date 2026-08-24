from __future__ import annotations

import json
from pathlib import Path

from conftest import load_etl_node


ROOT = Path(__file__).resolve().parents[2]
COMMON = load_etl_node("_common.py")


def test_migration_gold_is_well_formed_and_unique() -> None:
    fixture = json.loads(
        (ROOT / "fixtures/migration_gold.json").read_text(encoding="utf-8")
    )
    pages = fixture["edge_pages"]
    page_numbers = [entry["page"] for entry in pages]
    assert page_numbers == sorted(page_numbers)
    assert len(page_numbers) == len(set(page_numbers))
    assert all(entry["gates"] and entry["facts"] for entry in pages)


def test_non_negotiable_prior_cases_are_present() -> None:
    fixture = json.loads(
        (ROOT / "fixtures/migration_gold.json").read_text(encoding="utf-8")
    )
    by_page = {entry["page"]: entry for entry in fixture["edge_pages"]}
    required = {8, 11, 13, 115, 134, 195, 247, 452, 480, 680, 688}
    assert required.issubset(by_page)
    assert "source_raster_reads_424" in by_page[247]["facts"]
    assert "v1_pdf_patch_rejected" in by_page[247]["facts"]
    assert "source_amount_15100000" in by_page[138]["facts"]
    assert "source_bullet_3_period" in by_page[147]["facts"]
    assert "source_amount_21000000" in by_page[149]["facts"]
    assert "source_district_1_hyphen" in by_page[480]["facts"]
    assert "row_loss_at_150_dpi" in by_page[480]["facts"]
    assert "fap_funding_fold" in by_page[688]["facts"]


def test_all_historical_pdf_replacements_are_rejected() -> None:
    reviews = json.loads(
        (ROOT / "fixtures/pdf_patch_reviews.json").read_text(encoding="utf-8")
    )["reviews"]
    assert {review["page"] for review in reviews} == {138, 147, 149, 247, 480}
    assert all(review["status"] == "rejected" for review in reviews)


def test_carry_has_both_lattice_and_pap_spans() -> None:
    fixture = json.loads(
        (ROOT / "fixtures/migration_gold.json").read_text(encoding="utf-8")
    )
    spans = {entry["pages"] for entry in fixture["contiguous_spans"]}
    assert {"13-108", "115-690"}.issubset(spans)


def test_load_pages_from_migration_gold_edge_pages() -> None:
    pages = COMMON.load_pages_from_json(
        Path("fixtures/migration_gold.json"), "edge_pages"
    )
    assert pages[0] == 8
    assert 247 in pages
    assert 688 in pages
    assert pages == sorted(set(pages))


def test_load_pages_from_migration_gold_contiguous_spans() -> None:
    pages = COMMON.load_pages_from_json(
        Path("fixtures/migration_gold.json"), "contiguous_spans"
    )
    assert pages == list(range(13, 109)) + list(range(115, 691))


def test_load_pages_from_migration_gold_table_structure_spans() -> None:
    pages = COMMON.load_pages_from_json(
        Path("fixtures/migration_gold.json"), "table_structure_spans"
    )
    assert pages == list(range(105, 121))


def test_load_pages_from_migration_gold_by_ou_structure_spans() -> None:
    pages = COMMON.load_pages_from_json(
        Path("fixtures/migration_gold.json"), "by_ou_structure_spans"
    )
    assert pages == list(range(13, 29))


def test_reviewed_by_ou_seed_contract() -> None:
    fixture = json.loads(
        (ROOT / "fixtures/by_ou_table_seeds.json").read_text(encoding="utf-8")
    )
    table = fixture["tables"][0]
    assert table["table_id"] == "by-ou-001"
    assert table["start"] == {
        "page": 13,
        "page_header_band_ids": [0],
        "table_title_band_ids": [1],
        "column_header_band_ids": [2, 3, 4, 5, 6],
        "body_first_band_id": 7,
    }
    assert table["end"] == {
        "page": 108,
        "terminal_band_id": 9,
        "terminal_total_phrase_id": 26,
        "next_table_first_band_id": 10,
    }
    assert [item["role"] for item in table["column_seed"]["roles"]] == [
        "PS", "MOOE", "CO", "Total"
    ]
    assert table["hierarchy_seed"]["phrase_id"] == 13
    assert table["development_pages"] == [13, 14, 15]
    assert table["carry_policy"]["reset_on_gap"] is True
