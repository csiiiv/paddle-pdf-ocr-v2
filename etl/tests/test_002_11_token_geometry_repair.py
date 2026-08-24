from __future__ import annotations

from conftest import load_etl_node

node = load_etl_node("002.11-token-geometry-repair.py")
repair_page = node.repair_page


def phrase(pid, text, bbox, observation, *, band_id, right_anchor=True, **extra):
    payload = {"phrase_id": pid, "band_id": band_id, "text": text, "bbox": bbox,
               "observation": observation, "token_ids": [pid],
               "source_line_ids": [pid]}
    if right_anchor:
        payload["right_edge_anchor"] = {"raw_x": bbox[2]}
    payload.update(extra)
    return payload


def geometry_with(rows):
    grouped: dict[int, list[dict]] = {}
    for row in rows:
        grouped.setdefault(int(row["band_id"]), []).append(row)
    bands = []
    for band_id, members in sorted(grouped.items()):
        bands.append({
            "band_id": band_id,
            "bbox": [min(m["bbox"][0] for m in members),
                     min(m["bbox"][1] for m in members),
                     max(m["bbox"][2] for m in members),
                     max(m["bbox"][3] for m in members)],
            "baseline_y": max(m["bbox"][3] for m in members),
            "baseline_reference_x": 306.0,
            "baseline_correction_slope": 0.0,
            "token_ids": [int(m["phrase_id"]) for m in members],
            "phrase_ids": [int(m["phrase_id"]) for m in members],
        })
    return {
        "page_size_pt": [612, 792],
        "phrases": rows,
        "baseline_bands": bands,
        "column_candidates": [],
        "separator_candidates": [],
        "fit_candidates": [],
        "diagnostics": {"baseline_tolerance": 2.0, "median_token_height": 8.0},
    }


def healthy_rows(pairs, first_pid=0):
    rows = []
    pid = first_pid
    for label_bbox, amount_bbox, band_id in pairs:
        rows.append(phrase(pid, "Label " + str(pid), label_bbox, "text_candidate",
                           band_id=band_id,
                           text_candidate_type="main_text_candidate",
                           aligned_amount_phrase_ids=[pid + 1]))
        pid += 1
        rows.append(phrase(pid, "1,000,000", amount_bbox, "money_candidate",
                           band_id=band_id))
        pid += 1
    return rows


def test_clean_page_with_no_orphans_is_untouched():
    rows = healthy_rows([
        ([100, 20, 180, 30], [500, 18, 560, 28], 0),
        ([100, 40, 180, 50], [500, 38, 560, 48], 1),
        ([100, 60, 180, 70], [500, 58, 560, 68], 2),
    ])
    sample = geometry_with(rows)
    audit = repair_page(sample)
    assert audit["action"] == "none"
    assert audit["reason"] == "no_orphans"


def test_amounts_below_labels_page_fails_convention_gate():
    rows = healthy_rows([
        ([100, 20, 180, 30], [500, 23, 560, 33], 0),
        ([100, 40, 180, 50], [500, 43, 560, 53], 1),
        ([100, 60, 180, 70], [500, 63, 560, 73], 2),
    ])
    # Add an orphan so the orphan gate passes and the convention gate runs.
    rows.append(phrase(6, "Label D", [100, 80, 180, 90], "text_candidate",
                       band_id=3, text_candidate_type="wrapped_text_candidate"))
    rows.append(phrase(7, "5,000", [500, 78, 560, 88], "money_candidate",
                       band_id=3))
    sample = geometry_with(rows)
    audit = repair_page(sample)
    assert audit["action"] == "none"
    assert audit["reason"] == "amounts_not_above_labels_convention"
    assert audit["convention_median_delta_pt"] == 3.0


def chain_fixture():
    """Mirror p292: orphan above a contradicted thief above an unclaimed label.

    Ground truth: orphan p1 belongs to thief B (amounts ride above labels);
    evicted p3 belongs to the unclaimed label C below it. Vertical gaps
    mirror the real corpus: label tops sit -1..+5pt from amount bottoms.
    Three healthy pairs establish the page convention.
    """
    rows = [
        # Band 0: orphan amount alone.
        phrase(1, "1,000,000", [500, 18, 560, 28], "money_candidate", band_id=0),
        # Band 1: thief label B claims p3 whose top (30) starts below B's top (27).
        phrase(2, "Label B", [100, 27, 180, 37], "text_candidate", band_id=1,
               text_candidate_type="main_text_candidate",
               aligned_amount_phrase_ids=[3]),
        phrase(3, "2,000,000", [500, 30, 560, 40], "money_candidate", band_id=1),
        # Band 2: unclaimed label absorbs the cascade tail.
        phrase(4, "Label C", [100, 44, 180, 54], "text_candidate", band_id=2,
               text_candidate_type="wrapped_text_candidate"),
        # Healthy pairs (IDs 10+) for convention support.
        *healthy_rows([
            ([100, 60, 180, 70], [500, 51, 560, 61], 3),
            ([100, 80, 180, 90], [500, 71, 560, 81], 4),
            ([100, 100, 180, 110], [500, 91, 560, 101], 5),
        ], first_pid=10),
    ]
    rows.sort(key=lambda p: (p["bbox"][1], p["phrase_id"]))
    return rows


def test_chain_shift_is_repaired_and_bands_move():
    sample = geometry_with(chain_fixture())
    audit = repair_page(sample)
    assert audit["action"] == "repaired"
    assert audit["n_amounts_rebound"] == 2
    by_id = {p["phrase_id"]: p for p in sample["phrases"]}
    assert by_id[2]["aligned_amount_phrase_ids"] == [1]
    assert by_id[4]["aligned_amount_phrase_ids"] == [3]
    assert by_id[2]["text_candidate_type"] == "main_text_candidate"
    assert by_id[4]["text_candidate_type"] == "main_text_candidate"
    assert by_id[3]["band_id"] == 2
    bands = {b["band_id"]: b for b in sample["baseline_bands"]}
    assert 3 in [int(pid) for pid in bands[2]["phrase_ids"]]
    assert 3 not in [int(pid) for pid in bands[1]["phrase_ids"]]


def test_open_chain_is_flagged_not_applied():
    rows = [
        # Orphan, but the label below holds a HEALTHY claim: never steal.
        phrase(1, "1,000,000", [500, 18, 560, 28], "money_candidate", band_id=0),
        phrase(2, "Label B", [100, 27, 180, 37], "text_candidate", band_id=1,
               text_candidate_type="main_text_candidate",
               aligned_amount_phrase_ids=[3]),
        phrase(3, "2,000,000", [500, 25, 560, 35], "money_candidate", band_id=1),
        *healthy_rows([
            ([100, 60, 180, 70], [500, 51, 560, 61], 3),
            ([100, 80, 180, 90], [500, 71, 560, 81], 4),
            ([100, 100, 180, 110], [500, 91, 560, 101], 5),
        ], first_pid=10),
    ]
    rows.sort(key=lambda p: (p["bbox"][1], p["phrase_id"]))
    sample = geometry_with(rows)
    audit = repair_page(sample)
    assert audit["action"] == "none"
    assert audit["reason"] == "no_closed_chains"
    assert audit["n_chains_open"] == 1
    by_id = {p["phrase_id"]: p for p in sample["phrases"]}
    assert by_id[2]["aligned_amount_phrase_ids"] == [3]


def test_repair_is_idempotent():
    sample = geometry_with(chain_fixture())
    first = repair_page(sample)
    assert first["action"] == "repaired"
    second = repair_page(sample)
    assert second["action"] == "none"
    assert second["reason"] == "no_orphans"


def test_tail_promotion_promotes_the_absorbing_label():
    sample = geometry_with(chain_fixture())
    audit = repair_page(sample)
    assert audit["action"] == "repaired"
    assert audit["n_labels_promoted"] == 1


def test_fit_candidates_rebuilt_from_corrected_pairing():
    sample = geometry_with(chain_fixture())
    sample["column_candidates"] = [{
        "column_id": 0, "phrase_ids": [1, 3], "recurring": True,
        "right_x": 560.0, "left_line_segment": [500, 0, 500, 792],
    }]
    audit = repair_page(sample)
    assert audit["action"] == "repaired"
    fits = sample["fit_candidates"]
    assert len(fits) == 1
    # Post-repair pairing: 1->B, 3->C.
    assert fits[0]["n_pairs"] == 2
    assert [pair[0] for pair in fits[0]["pair_phrase_ids"]] == [2, 4]

