"""PAP label anatomy: title, description subtext, chainage, and GPS.

Pipeline order::

1. Split category title from subtext using label-cell line geometry + token gaps
2. Chainage preprocess + parse + strip
3. GPS parse + strip on the remainder

Subtext detection uses stage ``002.10`` gap measurements: when the first line of
a multi-line label cell ends with a wide run gap (label prose → amount column)
while later lines fill the cell normally, the PDF used a hard newline and the
remaining lines are description subtext — not word wrap.
"""

from __future__ import annotations

import re
from typing import Any

from .chainage import has_chainage_cue, parse_chainage
from .gps import parse_coordinates

# Wide run gap on the first label line (pt / estimated char spaces).
_MIN_RUN_GAP_PT = 72.0
_MIN_RUN_GAP_SPACES = 15.0

_PROSE_LEAD = re.compile(r"^(?:The|This)\s+")
_PROSE_VERB = re.compile(
    r"(?i)\b(is a sub-program|aims to|involves|encompasses|covers the|"
    r"focuses specifically|seeks to|program focuses|program aims)\b"
)
_FUNDING_LABEL = re.compile(r"^(?:GOP|Loan Proceeds|GOP Loan Proceeds)$", re.IGNORECASE)
_CHAINAGE_CONT = re.compile(r"(?i)^(?:K\d|[\d,]|Sta\.?\s*\d|Chainage\s*\d|C0\+|KM\d)")


def _normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def _phrase_token_ids(phrases: dict[int, dict[str, Any]], phrase_ids: list[int]) -> set[int]:
    tokens: set[int] = set()
    for phrase_id in phrase_ids:
        phrase = phrases.get(int(phrase_id))
        if not phrase:
            continue
        tokens.update(int(token_id) for token_id in (phrase.get("token_ids") or []))
    return tokens


def build_label_line_metrics(
    label_cell: dict[str, Any] | None,
    phrases: dict[int, dict[str, Any]],
    gaps: list[dict[str, Any]] | None,
) -> list[dict[str, Any]] | None:
    """Measure each label-cell line: fill, trailing gap, and run gap to non-line tokens."""
    if not label_cell:
        return None
    lines = label_cell.get("lines") or []
    bbox = label_cell.get("bbox")
    if len(lines) < 2 or not bbox or len(bbox) < 4:
        return None

    cell_x0 = float(bbox[0])
    cell_x1 = float(bbox[2])
    cell_width = max(cell_x1 - cell_x0, 1.0)
    gap_rows = gaps or []

    metrics: list[dict[str, Any]] = []
    for line in sorted(lines, key=lambda item: int(item.get("band_id", 0))):
        text = _normalize_space(line.get("text") or "")
        if not text:
            continue
        phrase_ids = [int(value) for value in line.get("phrase_ids") or []]
        line_tokens = _phrase_token_ids(phrases, phrase_ids)
        xs: list[float] = []
        x1s: list[float] = []
        for phrase_id in phrase_ids:
            phrase = phrases.get(phrase_id)
            if not phrase:
                continue
            box = phrase.get("bbox") or []
            if len(box) < 4:
                continue
            xs.append(float(box[0]))
            x1s.append(float(box[2]))
        if not xs:
            continue

        band_id = int(line.get("band_id", -1))
        run_gap_pt = 0.0
        run_gap_spaces = 0.0
        for gap in gap_rows:
            if int(gap.get("band_id", -1)) != band_id:
                continue
            left_token = int(gap.get("left_token_id", -1))
            right_token = int(gap.get("right_token_id", -1))
            if left_token not in line_tokens or right_token in line_tokens:
                continue
            gap_pt = float(gap.get("gap_pt") or 0.0)
            if gap_pt >= run_gap_pt:
                run_gap_pt = gap_pt
                run_gap_spaces = float(gap.get("estimated_spaces") or 0.0)

        x0, x1 = min(xs), max(x1s)
        trail_gap_pt = cell_x1 - x1
        metrics.append({
            "text": text,
            "band_id": band_id,
            "fill": (x1 - x0) / cell_width,
            "run_gap_pt": round(run_gap_pt, 3),
            "run_gap_spaces": round(run_gap_spaces, 3),
            "trail_gap_pt": round(trail_gap_pt, 3),
        })

    return metrics if len(metrics) >= 2 else None


def _is_prose_subtext_start(text: str) -> bool:
    cleaned = (text or "").strip()
    if not cleaned:
        return False
    if _PROSE_LEAD.match(cleaned):
        return True
    return bool(_PROSE_VERB.search(cleaned[:200]))


def _is_chainage_continuation(text: str) -> bool:
    return bool(_CHAINAGE_CONT.match((text or "").strip()))


def _is_funding_label(text: str) -> bool:
    return bool(_FUNDING_LABEL.match((text or "").strip()))


def split_title_description_geometry(
    metrics: list[dict[str, Any]] | None,
) -> tuple[str, str | None] | None:
    """Split when line 1 has a wide token gap to the amount and line 2 is prose."""
    if not metrics or len(metrics) < 2:
        return None

    first = metrics[0]
    second = metrics[1]
    wide_run = (
        first["run_gap_pt"] >= _MIN_RUN_GAP_PT
        or first["run_gap_spaces"] >= _MIN_RUN_GAP_SPACES
    )
    if not wide_run:
        return None
    if has_chainage_cue(first["text"]) or _is_chainage_continuation(second["text"]):
        return None
    if _is_funding_label(first["text"]) or _is_funding_label(second["text"]):
        return None
    if not _is_prose_subtext_start(second["text"]):
        return None

    title = first["text"]
    description = _normalize_space(" ".join(line["text"] for line in metrics[1:]))
    return title, description or None


def split_title_description(
    text: str,
    *,
    line_metrics: list[dict[str, Any]] | None = None,
) -> tuple[str, str | None]:
    """Split category title from description subtext."""
    geometry = split_title_description_geometry(line_metrics)
    if geometry:
        return geometry

    normalized = _normalize_space(text)
    return normalized, None


def enrich_pap_label(
    label: str,
    *,
    label_raw: str | None = None,
    line_metrics: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    raw = (label_raw or label or "").strip()
    collapsed = _normalize_space(raw)
    if not collapsed:
        return {
            "label": "",
            "label_ocr": None,
            "description": None,
            "chainages": None,
            "coordinates": None,
        }

    title, description = split_title_description(collapsed, line_metrics=line_metrics)
    all_chainages: list[Any] = []
    all_coordinates: list[Any] = []

    stripped_title = title or collapsed
    chainage = parse_chainage(stripped_title)
    if chainage.ok:
        stripped_title = chainage.label_title
        all_chainages.extend(chainage.chainages)

    stripped_description = description
    if description:
        desc_chainage = parse_chainage(description)
        if desc_chainage.ok:
            stripped_description = (desc_chainage.label_title or "").strip() or None
            all_chainages.extend(desc_chainage.chainages)

    gps = parse_coordinates(stripped_title)
    if gps.ok:
        stripped_title = gps.label_title
        all_coordinates.extend(gps.coordinates)

    if stripped_description:
        desc_gps = parse_coordinates(stripped_description)
        if desc_gps.ok:
            stripped_description = (desc_gps.label_title or "").strip() or None
            all_coordinates.extend(desc_gps.coordinates)

    touched = bool(description or all_chainages or all_coordinates)
    return {
        "label": stripped_title if touched else collapsed,
        "label_ocr": raw if touched else None,
        "description": stripped_description,
        "chainages": [span.to_dict() for span in all_chainages] if all_chainages else None,
        "coordinates": [coord.to_dict() for coord in all_coordinates] if all_coordinates else None,
    }


def apply_label_anatomy(nodes: list[dict[str, Any]]) -> dict[str, int]:
    stats = {"n_stripped": 0, "n_description": 0, "n_chainage": 0, "n_gps": 0}
    for node in nodes:
        raw = node.get("label") or ""
        if not str(raw).strip():
            continue
        enriched = enrich_pap_label(
            str(raw),
            label_raw=node.get("label_raw"),
            line_metrics=node.get("label_line_metrics"),
        )
        if not enriched["label_ocr"]:
            continue
        node["label_ocr"] = enriched["label_ocr"]
        node["label"] = enriched["label"]
        stats["n_stripped"] += 1
        if enriched["description"]:
            node["description"] = enriched["description"]
            stats["n_description"] += 1
        if enriched["chainages"]:
            node["chainages"] = enriched["chainages"]
            stats["n_chainage"] += 1
        if enriched["coordinates"]:
            node["coordinates"] = enriched["coordinates"]
            stats["n_gps"] += 1
    return stats
