from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_migration_gold_is_well_formed_and_unique() -> None:
    fixture = json.loads(
        (ROOT / "fixtures/migration_gold.json").read_text(encoding="utf-8")
    )
    pages = fixture["pages"]
    page_numbers = [entry["page"] for entry in pages]
    assert page_numbers == sorted(page_numbers)
    assert len(page_numbers) == len(set(page_numbers))
    assert all(entry["gates"] and entry["facts"] for entry in pages)


def test_non_negotiable_prior_cases_are_present() -> None:
    fixture = json.loads(
        (ROOT / "fixtures/migration_gold.json").read_text(encoding="utf-8")
    )
    by_page = {entry["page"]: entry for entry in fixture["pages"]}
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
    assert {"13-20", "115-130"}.issubset(spans)
