"""Archived region/zone assignment used by retired layout and cell nodes."""

from __future__ import annotations

from typing import Any

LABEL_PRIORITY = {
    "table": 0, "text": 1, "content": 1, "paragraph_title": 2,
    "figure_title": 2, "doc_title": 2, "formula": 3, "chart": 3,
    "image": 4, "header": 5, "footer": 5, "number": 5,
    "footnote": 5, "aside_text": 5,
}


def best_region(bbox: list[float] | None, regions: list[dict[str, Any]]) -> int | None:
    if not bbox or len(bbox) < 4:
        return None
    best_id: int | None = None
    best_key: tuple[float, int] | None = None
    for region in regions:
        target = region["bbox"]
        x_overlap = max(0.0, min(bbox[2], target[2]) - max(bbox[0], target[0]))
        y_overlap = max(0.0, min(bbox[3], target[3]) - max(bbox[1], target[1]))
        if x_overlap <= 0 or y_overlap <= 0:
            center_x = (bbox[0] + bbox[2]) / 2
            center_y = (bbox[1] + bbox[3]) / 2
            if not (target[0] <= center_x <= target[2] and target[1] <= center_y <= target[3]):
                continue
            area = 1.0
        else:
            area = x_overlap * y_overlap
        key = (area, -LABEL_PRIORITY.get(region["label"], 9))
        if best_key is None or key > best_key:
            best_key = key
            best_id = int(region["region_id"])
    return best_id


def assign_regions(tokens: list[dict[str, Any]], lines: list[dict[str, Any]], regions: list[dict[str, Any]]) -> dict[str, Any]:
    region_by_id = {region["region_id"]: region for region in regions}
    for token in tokens:
        region_id = best_region(token.get("bbox"), regions)
        token["region_id"] = region_id
        token["chrome"] = bool(region_id is not None and region_by_id[region_id].get("chrome"))
    for line in lines:
        region_id = best_region(line.get("bbox"), regions)
        votes: dict[int | None, int] = {}
        for token_id in line.get("token_ids") or []:
            if 0 <= token_id < len(tokens):
                vote = tokens[token_id].get("region_id")
                votes[vote] = votes.get(vote, 0) + 1
        if votes:
            region_id = max(votes, key=lambda value: votes[value])
        line["region_id"] = region_id
        line["chrome"] = bool(region_id is not None and region_by_id[region_id].get("chrome"))
    zones = []
    for region in regions:
        if region.get("chrome"):
            continue
        region_id = region["region_id"]
        token_ids = [i for i, token in enumerate(tokens) if token.get("region_id") == region_id]
        line_ids = [line["line_id"] for line in lines if line.get("region_id") == region_id and line.get("line_id") is not None]
        zones.append({
            "zone_id": len(zones), "region_id": region_id, "label": region["label"],
            "bbox": list(region["bbox"]), "score": region["score"],
            "n_tokens": len(token_ids), "n_lines": len(line_ids),
            "token_ids": token_ids, "line_ids": line_ids,
        })
    return {"zones": zones,
            "n_chrome_tokens": sum(token.get("chrome", False) for token in tokens),
            "n_unassigned_tokens": sum(token.get("region_id") is None for token in tokens)}
