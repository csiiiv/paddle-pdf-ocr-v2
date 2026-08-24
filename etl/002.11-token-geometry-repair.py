#!/usr/bin/env python3
"""Stage 002.11: Repair dislocated label-amount pairing chains.

Inputs: 002.10 token-geometry layer pages
Outputs: 002.11 repaired token-geometry pages + qa/summary.json

Where the print convention rests amount baselines slightly ABOVE label
baselines, a banding glitch can bind each amount to the NEXT row's label.
Because every amount column entry has a partner main label, a dislocation
leaves orphans (money anchors no label claims) and claims that contradict
the page-wide convention (the claimed amount's top starts BELOW the label's
top). Those two signals identify the break deterministically:

  orphan -> thief label (contradicted claim) -> evicted amount
          -> next thief ... -> unclaimed label absorbs the tail

A chain is applied only if it closes without stealing from any healthy
pair; the walk never crosses a label already used by another chain. Clean
pages are copied unchanged into this stage's layer. Chains that cannot
close are flagged in the stage QA for review.
"""
from __future__ import annotations

import argparse
import statistics
import time
from typing import Any

from _common import add_stage_arguments, make_context, require_pass
from _shared.artifacts import read_json, write_json_atomic
from _shared.contracts import stamp_meta
from _shared.timestamps import iso_now

PRODUCER = "token_geometry_pairing_repair_v1"

PARAMETERS = {
    # Convention gate: the page must show at least this many claimed pairs
    # whose median delta (amount bottom - label bottom) is at or below this
    # value, i.e. amounts systematically ride above labels.
    "convention_min_pairs": 3,
    "convention_median_delta_max_pt": -0.5,
    # A claim is contradicted when the amount's TOP starts below the label's
    # TOP by more than this slack. Healthy pairs put the amount top at or
    # above the label top.
    "claim_contradiction_slack_pt": 0.5,
    # Walk overlap slack: the next label's top may rise this far above the
    # current amount's bottom and still count as "the label below it".
    "walk_overlap_slack_pt": 3.0,
    # Walk distance cap: a label starting further than this below the
    # current amount is not an adjacent row partner. Genuine dislocations
    # put the label top within ~6.5pt of the amount bottom (rows nearly
    # touch); header rows sit ~10pt+ below (p108 year headers).
    "walk_max_gap_pt": 8.0,
    # Mirrors 002.10 column_min_members for fit review flags.
    "column_min_members": 3,
}


def _median(values: list[float], default: float = 0.0) -> float:
    return float(statistics.median(values)) if values else default


def _mad(values: list[float]) -> float:
    center = _median(values)
    return _median([abs(value - center) for value in values])


def _line_fit(points: list[tuple[float, float]]) -> tuple[float, float]:
    if len(points) < 2:
        return 0.0, (points[0][1] if points else 0.0)
    xm = statistics.fmean(x for x, _ in points)
    ym = statistics.fmean(y for _, y in points)
    denominator = sum((x - xm) ** 2 for x, _ in points)
    slope = (sum((x - xm) * (y - ym) for x, y in points) / denominator
             if denominator else 0.0)
    return slope, ym - slope * xm


def _top(phrase: dict[str, Any]) -> float:
    return float(phrase["bbox"][1])


def _bottom(phrase: dict[str, Any]) -> float:
    return float(phrase["bbox"][3])


def _refit_band(band: dict[str, Any], by_id: dict[int, dict[str, Any]],
                tokens: list[dict[str, Any]], *, tolerance: float,
                median_height: float) -> None:
    """Refit a band whose membership changed from its member phrases.

    Mirrors 002.10: corrected bottoms use the band's own slope correction,
    the segment fits raw token bottoms, and per-token assignments recompute
    with the same bottom/overlap/height scoring.
    """
    token_ids = sorted({int(token_id)
                        for phrase_id in band.get("phrase_ids") or []
                        for token_id in (by_id[int(phrase_id)].get("token_ids") or [])})
    boxes = [tokens[index]["bbox"] for index in token_ids
             if index < len(tokens) and tokens[index].get("bbox")]
    if not boxes:
        return
    reference_x = float(band.get("baseline_reference_x") or 0.0)
    slope = float(band.get("baseline_correction_slope") or 0.0)
    corrected = [float(box[3]) - slope * (((float(box[0]) + float(box[2])) / 2) - reference_x)
                 for box in boxes]
    baseline_y = _median(corrected)
    raw_points = [((float(box[0]) + float(box[2])) / 2, float(box[3])) for box in boxes]
    fit_slope, intercept = _line_fit(raw_points)
    residuals = [abs(y - (fit_slope * x + intercept)) for x, y in raw_points]
    bbox = [round(min(float(box[0]) for box in boxes), 2),
            round(min(float(box[1]) for box in boxes), 2),
            round(max(float(box[2]) for box in boxes), 2),
            round(max(float(box[3]) for box in boxes), 2)]
    height = _median([float(box[3]) - float(box[1]) for box in boxes], median_height)
    representative = [bbox[0], baseline_y - height, bbox[2], baseline_y]

    assignments = []
    for index, box in zip(token_ids, boxes):
        center_x = (float(box[0]) + float(box[2])) / 2
        corrected_bottom = float(box[3]) - slope * (center_x - reference_x)
        delta = abs(corrected_bottom - baseline_y)
        bottom_score = max(0.0, 1.0 - delta / max(tolerance, 0.01))
        shorter = max(min(float(box[3]) - float(box[1]), height), 0.01)
        overlap = max(0.0, min(box[3], representative[3]) - max(box[1], representative[1])) / shorter
        height_score = max(0.0, 1.0 - abs((float(box[3]) - float(box[1])) - height)
                          / max(height, 0.01))
        assignments.append({"token_id": index, "bottom_delta": round(delta, 3),
                            "raw_bottom": round(float(box[3]), 3),
                            "corrected_bottom": round(corrected_bottom, 3),
                            "vertical_overlap": round(overlap, 3),
                            "height_compatibility": round(height_score, 3),
                            "confidence": round(.55 * bottom_score + .30 * overlap
                                                + .15 * height_score, 3)})

    band.update({
        "token_ids": token_ids, "bbox": bbox,
        "baseline_y": round(baseline_y, 3),
        "baseline_segment": [bbox[0], round(fit_slope * bbox[0] + intercept, 3),
                             bbox[2], round(fit_slope * bbox[2] + intercept, 3)],
        "fit_slope": round(fit_slope, 7), "fit_mad": round(_mad(residuals), 3),
        "assignments": assignments,
        "source_line_ids": sorted({int(line_id)
                                   for phrase_id in band.get("phrase_ids") or []
                                   for line_id in (by_id[int(phrase_id)].get("source_line_ids") or [])}),
    })


def _walk_chains(orphans: list[dict[str, Any]], labels: list[dict[str, Any]],
                 claims: dict[int, list[int]], by_id: dict[int, dict[str, Any]],
                 audit: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Trace orphan -> thief -> evicted chains; return (closed, open)."""
    slack = PARAMETERS["claim_contradiction_slack_pt"]
    overlap = PARAMETERS["walk_overlap_slack_pt"]
    max_gap = PARAMETERS["walk_max_gap_pt"]

    def contradicted(label: dict[str, Any]) -> int | None:
        for amount_id in claims.get(int(label["phrase_id"]), []):
            if _top(by_id[amount_id]) > _top(label) + slack:
                return amount_id
        return None

    closed_chains: list[dict[str, Any]] = []
    open_chains: list[dict[str, Any]] = []
    used_labels: set[int] = set()
    for orphan in sorted(orphans, key=lambda p: (_bottom(p), int(p["phrase_id"]))):
        current = orphan
        steps: list[dict[str, Any]] = []
        chain_labels: list[int] = []
        resolved = False
        while True:
            below = [label for label in labels
                     if _bottom(current) - overlap <= _top(label)
                     <= _bottom(current) + max_gap
                     and int(label["phrase_id"]) not in used_labels]
            if not below:
                break
            target = below[0]
            target_id = int(target["phrase_id"])
            if target_id in chain_labels:
                break
            target_claims = claims.get(target_id) or []
            if not target_claims:
                steps.append({"amount_phrase_id": int(current["phrase_id"]),
                              "label_phrase_id": target_id, "kind": "tail_absorbed"})
                chain_labels.append(target_id)
                resolved = True
                break
            if len(target_claims) > 1:
                # Multi-claim thieves need a parallel cascade model; flag only.
                break
            evicted = target_claims[0]
            if _top(by_id[evicted]) > _top(target) + slack:
                steps.append({"amount_phrase_id": int(current["phrase_id"]),
                              "label_phrase_id": target_id,
                              "kind": "steal_from_contradicted"})
                chain_labels.append(target_id)
                current = by_id[evicted]
                continue
            break  # Healthy claim: never steal.
        if resolved:
            closed_chains.append({
                "orphan_amount_phrase_id": int(orphan["phrase_id"]),
                "steps": steps, "labels": chain_labels})
            used_labels.update(chain_labels)
        else:
            open_chains.append({"orphan_amount_phrase_id": int(orphan["phrase_id"]),
                                "steps": steps})
    audit["n_chains_closed"] = len(closed_chains)
    audit["n_chains_open"] = len(open_chains)
    return closed_chains, open_chains


def _rebuild_dependents(geometry: dict[str, Any], by_id: dict[int, dict[str, Any]],
                        claimable: list[dict[str, Any]]) -> None:
    """Rebuild separators and column fits from the corrected pairing.

    Both measurements are derived from band co-membership plus the
    label/amount relation, so the pre-repair values would contradict the
    corrected pairing and re-tilt the downstream row boundaries.
    """
    bands = {int(band["band_id"]): band
             for band in geometry.get("baseline_bands") or []}
    non_amount = {"marker_candidate", "money_candidate", "code_candidate"}

    def left_peers(amount: dict[str, Any]) -> list[dict[str, Any]]:
        return [by_id[int(phrase_id)]
                for phrase_id in (bands[int(amount["band_id"])].get("phrase_ids") or [])
                if float(by_id[int(phrase_id)]["bbox"][2]) < float(amount["bbox"][0])
                and by_id[int(phrase_id)].get("observation") not in non_amount]

    separators: list[dict[str, Any]] = []
    for amount in claimable:
        peers = left_peers(amount)
        if not peers:
            continue
        label = max(peers, key=lambda p: float(p["bbox"][2]))
        left, right = float(label["bbox"][2]), float(amount["bbox"][0])
        if right <= left:
            continue
        y0 = min(_top(label), _top(amount))
        y1 = max(_bottom(label), _bottom(amount))
        x = (left + right) / 2
        separators.append({"separator_id": len(separators),
                           "band_id": int(amount["band_id"]),
                           "label_phrase_id": int(label["phrase_id"]),
                           "amount_phrase_id": int(amount["phrase_id"]),
                           "x": round(x, 3), "gap_pt": round(right - left, 3),
                           "line_segment": [round(x, 2), round(y0, 2),
                                            round(x, 2), round(y1, 2)],
                           "review": True})
    geometry["separator_candidates"] = separators

    fits: list[dict[str, Any]] = []
    for column in geometry.get("column_candidates") or []:
        pair_ids: list[list[int]] = []
        segments: list[list[float]] = []
        slopes: list[float] = []
        for amount_id in column.get("phrase_ids") or []:
            amount = by_id[int(amount_id)]
            peers = left_peers(amount)
            if not peers:
                continue
            label = min(peers, key=lambda p: float(p["bbox"][0]))
            lx = (float(label["bbox"][0]) + float(label["bbox"][2])) / 2
            ly = _bottom(label)
            ax = (float(amount["bbox"][0]) + float(amount["bbox"][2])) / 2
            ay = _bottom(amount)
            if ax - lx < 40:
                continue
            slopes.append((ay - ly) / (ax - lx))
            pair_ids.append([int(label["phrase_id"]), int(amount_id)])
            segments.append([round(lx, 2), round(ly, 2), round(ax, 2), round(ay, 2)])
        fits.append({"fit_id": len(fits), "column_id": int(column["column_id"]),
                     "slope": round(_median(slopes), 7),
                     "slope_mad": round(_mad(slopes), 7),
                     "n_pairs": len(slopes),
                     "pair_phrase_ids": pair_ids, "segments": segments,
                     "review": len(slopes) < PARAMETERS["column_min_members"]})
    geometry["fit_candidates"] = fits


def repair_page(geometry: dict[str, Any],
                tokens: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Repair pairing chains on one page artifact; return an audit record.

    The geometry dict is mutated only when at least one chain closes; pages
    that fail the gates are returned untouched so clean pages stay
    byte-identical and reruns stay idempotent.
    """
    phrases = geometry.get("phrases") or []
    by_id = {int(phrase["phrase_id"]): phrase for phrase in phrases}
    # Only column-anchor money phrases participate in pairing (002.10 stamps
    # right_edge_anchor on exactly that set); guard on the observation too so
    # the orphan scan never mistakes a stamped label for an amount.
    claimable = [phrase for phrase in phrases
                 if phrase.get("right_edge_anchor")
                 and phrase.get("observation") == "money_candidate"]

    claims: dict[int, list[int]] = {}
    for phrase in phrases:
        amount_ids = [int(value) for value in (phrase.get("aligned_amount_phrase_ids") or [])]
        if amount_ids:
            claims[int(phrase["phrase_id"])] = amount_ids
    claimed = {amount_id for amount_ids in claims.values() for amount_id in amount_ids}
    orphans = [phrase for phrase in claimable
               if int(phrase["phrase_id"]) not in claimed]

    deltas = [_bottom(by_id[amount_id]) - _bottom(by_id[label_id])
              for label_id, amount_ids in claims.items() for amount_id in amount_ids]
    audit: dict[str, Any] = {
        "producer": PRODUCER, "parameters": PARAMETERS,
        "upstream_producer": (geometry.get("artifact") or {}).get("producer"),
        "n_claimable_amounts": len(claimable), "n_orphans": len(orphans),
        "n_claims": len(deltas),
        "convention_median_delta_pt": round(_median(deltas), 3) if deltas else None,
    }

    if not orphans:
        audit.update(action="none", reason="no_orphans")
        return audit
    if len(deltas) < PARAMETERS["convention_min_pairs"]:
        audit.update(action="none", reason="insufficient_convention_support")
        return audit
    if _median(deltas) > PARAMETERS["convention_median_delta_max_pt"]:
        audit.update(action="none", reason="amounts_not_above_labels_convention")
        return audit

    labels = sorted((phrase for phrase in phrases
                     if phrase.get("observation") in {"text_candidate", "mixed_candidate"}),
                    key=lambda p: (_top(p), int(p["phrase_id"])))
    closed_chains, open_chains = _walk_chains(orphans, labels, claims, by_id, audit)
    if not closed_chains:
        audit.update(action="none", reason="no_closed_chains",
                     open_chains=open_chains)
        return audit

    rebinds: dict[int, int] = {}
    for chain in closed_chains:
        for step in chain["steps"]:
            rebinds[int(step["amount_phrase_id"])] = int(step["label_phrase_id"])

    touched_labels = set(rebinds.values())
    for label_id in touched_labels:
        by_id[label_id]["aligned_amount_phrase_ids"] = []
    for amount_id, label_id in rebinds.items():
        label = by_id[label_id]
        label["aligned_amount_phrase_ids"] = sorted(
            set(label.get("aligned_amount_phrase_ids") or []) | {amount_id})
    for phrase in phrases:
        if phrase.get("observation") in {"text_candidate", "mixed_candidate"}:
            phrase["text_candidate_type"] = (
                "main_text_candidate"
                if phrase.get("aligned_amount_phrase_ids")
                else "wrapped_text_candidate")

    bands = {int(band["band_id"]): band for band in geometry.get("baseline_bands") or []}
    band_moves: list[dict[str, Any]] = []
    for amount_id, label_id in rebinds.items():
        old_band = int(by_id[amount_id]["band_id"])
        new_band = int(by_id[label_id]["band_id"])
        if old_band == new_band or old_band not in bands or new_band not in bands:
            continue
        bands[old_band]["phrase_ids"] = [phrase_id
                                         for phrase_id in (bands[old_band].get("phrase_ids") or [])
                                         if int(phrase_id) != amount_id]
        bands[new_band]["phrase_ids"] = sorted(
            (bands[new_band].get("phrase_ids") or []) + [amount_id])
        by_id[amount_id]["band_id"] = new_band
        band_moves.append({"amount_phrase_id": amount_id,
                           "from_band_id": old_band, "to_band_id": new_band})
    if tokens is not None:
        diagnostics = geometry.get("diagnostics") or {}
        tolerance = float(diagnostics.get("baseline_tolerance") or 2.0)
        median_height = float(diagnostics.get("median_token_height") or 8.0)
        moved_bands = {move["from_band_id"] for move in band_moves} | {
            move["to_band_id"] for move in band_moves}
        for band in bands.values():
            if int(band["band_id"]) in moved_bands and band.get("phrase_ids"):
                _refit_band(band, by_id, tokens, tolerance=tolerance,
                            median_height=median_height)

    _rebuild_dependents(geometry, by_id, claimable)

    diagnostics = geometry.get("diagnostics") or {}
    diagnostics["n_main_text_candidates"] = sum(
        phrase.get("text_candidate_type") == "main_text_candidate" for phrase in phrases)
    diagnostics["n_wrapped_text_candidates"] = sum(
        phrase.get("text_candidate_type") == "wrapped_text_candidate" for phrase in phrases)
    confidences = [assignment["confidence"]
                   for band in bands.values()
                   for assignment in (band.get("assignments") or [])]
    if confidences:
        diagnostics["mean_assignment_confidence"] = round(
            statistics.fmean(confidences), 4)

    audit.update(action="repaired", reason="closed_chains_applied",
                 n_amounts_rebound=len(rebinds),
                 n_labels_promoted=sum(1 for label_id in touched_labels
                                       if not claims.get(label_id)),
                 rebindings=[{"amount_phrase_id": amount_id, "label_phrase_id": label_id}
                             for amount_id, label_id in sorted(rebinds.items())],
                 band_moves=band_moves, chains=closed_chains,
                 open_chains=open_chains)
    return audit


def run_stage(context) -> dict[str, Any]:
    results = []
    started_at, started = iso_now(), time.perf_counter()
    for page_no in context.pages:
        page_started_at, page_started = iso_now(), time.perf_counter()
        try:
            geometry = read_json(context.store.layer_path("token_geometry", page_no))
            paddle = read_json(context.store.layer_path("paddle", page_no))
            audit = repair_page(geometry, tokens=paddle.get("tokens") or [])
            stamp_meta(geometry, stage="layer:token_geometry_repair", producer=PRODUCER)
            geometry["pairing_repair"] = audit
            write_json_atomic(
                context.store.layer_path("token_geometry_repair", page_no), geometry)
            result = {"page": page_no, "pass": True, "action": audit["action"],
                      "reason": audit.get("reason"), "n_orphans": audit["n_orphans"],
                      "n_chains_closed": audit.get("n_chains_closed", 0),
                      "n_chains_open": audit.get("n_chains_open", 0),
                      "n_amounts_rebound": audit.get("n_amounts_rebound", 0)}
        except Exception as error:
            result = {"page": page_no, "pass": False,
                      "error_type": type(error).__name__, "error": str(error)}
        result.update({"started_at": page_started_at, "completed_at": iso_now(),
                       "timestamp_source": "captured",
                       "elapsed_s": round(time.perf_counter() - page_started, 3)})
        results.append(result)
    n_fail = sum(not result["pass"] for result in results)
    summary = {"artifact_version": 1, "gate": "TOKEN_GEOMETRY_PAIRING_REPAIR",
               "name": "deterministic_pairing_chain_repair",
               "scope": "repair_insert_v1", "producer": PRODUCER,
               "n_pages": len(results), "n_fail": n_fail,
               "n_repaired_pages": sum(result.get("action") == "repaired" for result in results),
               "n_open_chain_pages": sum(int(result.get("n_chains_open") or 0) > 0
                                         for result in results),
               "started_at": started_at, "completed_at": iso_now(),
               "timestamp_source": "captured",
               "elapsed_s": round(time.perf_counter() - started, 3),
               "pages": results, "pass": n_fail == 0}
    write_json_atomic(context.store.stage_qa_path("token_geometry_repair"), summary)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    add_stage_arguments(parser)
    summary = run_stage(make_context(parser.parse_args()))
    print(f"002.11 Pairing repair: pages={summary['n_pages']} "
          f"repaired={summary['n_repaired_pages']} "
          f"open_chain_pages={summary['n_open_chain_pages']} "
          f"fail={summary['n_fail']} elapsed={summary['elapsed_s']}s")
    require_pass(summary)


if __name__ == "__main__":
    main()
