"""PAP label GPS / coordinate parse: strip from title, store structured field.

See ``docs/gps.md``. Companion to ``chainage.py``; composed via
``project_desc.enrich_project_label`` (**after** chainage strip).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

# Letter → digit inside coordinate numeric runs only.
_LETTER_DIGIT = str.maketrans(
    {
        "O": "0",
        "o": "0",
        "I": "1",
        "l": "1",
        "L": "1",
        "|": "1",
        "S": "5",
        "s": "5",
        "B": "8",
        "Z": "2",
        "z": "2",
        "G": "6",
    }
)

# Decimal with optional spaces / OCR letters (e.g. 14.S64132, 124. 783, or plain 11)
_DEC = r"[0-9OIlLSBZGsboz|]{1,3}(?:\s*\.\s*[0-9OIlLSBZGsboz|]+)?"
_DEG = r"[°º]"
_HEM_NS = r"[NSns]"
_HEM_EW = r"[EWew]"
# Standalone hemisphere letters (not glued into place names)
_HEM_NS_TOK = rf"(?<![A-Za-z]){_HEM_NS}(?![A-Za-z])"
_HEM_EW_TOK = rf"(?<![A-Za-z]){_HEM_EW}(?![A-Za-z])"

# PH WGS84-ish sanity windows
_LAT_LO, _LAT_HI = 4.0, 22.0
_LON_LO, _LON_HI = 116.0, 128.0


def _fix_digits(s: str) -> str:
    return (s or "").translate(_LETTER_DIGIT)


def _parse_decimal(raw: str) -> float | None:
    t = _fix_digits(re.sub(r"\s+", "", raw or ""))
    if not t:
        return None
    try:
        return float(t)
    except ValueError:
        return None


def _looks_geo_pair(a: float, b: float) -> bool:
    """Strict PH WGS84 windows only (no soft fallback — avoids Sta. false hits)."""
    return (_LAT_LO <= a <= _LAT_HI and _LON_LO <= b <= _LON_HI) or (
        _LON_LO <= a <= _LON_HI and _LAT_LO <= b <= _LAT_HI
    )


def _has_fraction(raw: str) -> bool:
    return "." in (raw or "")


def _has_ascii_digit(raw: str) -> bool:
    return any(ch.isdigit() for ch in (raw or ""))


def _order_lat_lon(
    a: float, b: float, *, a_hem: str | None = None, b_hem: str | None = None
) -> tuple[float, float, bool]:
    """Return (lat, lon, swapped). Prefer hemisphere; else PH bounds."""
    if a_hem and b_hem:
        ah, bh = a_hem.upper(), b_hem.upper()
        if ah in "NS" and bh in "EW":
            lat = -abs(a) if ah == "S" else abs(a)
            lon = -abs(b) if bh == "W" else abs(b)
            return lat, lon, False
        if ah in "EW" and bh in "NS":
            lon = -abs(a) if ah == "W" else abs(a)
            lat = -abs(b) if bh == "S" else abs(b)
            return lat, lon, True

    a_lat = _LAT_LO <= a <= _LAT_HI
    b_lon = _LON_LO <= b <= _LON_HI
    a_lon = _LON_LO <= a <= _LON_HI
    b_lat = _LAT_LO <= b <= _LAT_HI
    if a_lat and b_lon:
        return a, b, False
    if a_lon and b_lat:
        return b, a, True
    # Soft fallback only for ordering after hemisphere / when one side is
    # slightly out of window — acceptance still uses ``_looks_geo_pair``.
    if a <= 35 and b >= 100:
        return a, b, False
    if a >= 100 and b <= 35:
        return b, a, True
    return a, b, False


def _dms_to_decimal(deg: str, minutes: str, seconds: str, hem: str) -> float | None:
    d = _parse_decimal(deg)
    m = _parse_decimal(minutes)
    s = _parse_decimal(seconds)
    if d is None or m is None or s is None:
        return None
    if not (0 <= m < 60 and 0 <= s < 60):
        return None
    val = abs(d) + m / 60.0 + s / 3600.0
    if hem.upper() in "SW":
        val = -val
    return val


def _split_glued_mmss(blob: str) -> tuple[str, str] | None:
    """``5154.78`` / ``5306`` → minutes + seconds (OCR dropped ``'``)."""
    t = _fix_digits(re.sub(r"\s+", "", blob or ""))
    if not t or not any(ch.isdigit() for ch in t):
        return None
    if "." in t:
        whole, frac = t.split(".", 1)
    else:
        whole, frac = t, None
    if len(whole) < 3 or len(whole) > 4:
        return None
    mm = whole[:-2]
    ss = whole[-2:] + (("." + frac) if frac is not None else "")
    if not mm or len(mm) > 2:
        return None
    return mm, ss


def _repair_ph_pair(a: float, b: float) -> tuple[float, float] | None:
    """Fix common OCR lon truncation ``24.813`` → ``124.813`` when peer is PH lat."""
    candidates = [(a, b)]
    # Leading ``1`` dropped from lon (120–128 → 20–28)
    if 20.0 <= a <= 29.0:
        candidates.append((a + 100.0, b))
    if 20.0 <= b <= 29.0:
        candidates.append((a, b + 100.0))
    for x, y in candidates:
        if _looks_geo_pair(x, y):
            return x, y
    return None


@dataclass
class Coordinate:
    lat: float | None
    lon: float | None
    raw: str
    kind: str = "decimal"  # decimal | dms | decimal_hem
    role: str | None = None  # LS | RS | None
    swapped: bool = False
    incomplete: bool = False
    orig_start: int = 0
    orig_end: int = 0

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"raw": self.raw}
        if self.lat is not None:
            d["lat"] = round(self.lat, 7)
        if self.lon is not None:
            d["lon"] = round(self.lon, 7)
        d["kind"] = self.kind
        if self.role:
            d["role"] = self.role
        if self.swapped:
            d["swapped"] = True
        if self.incomplete:
            d["incomplete"] = True
        return d


@dataclass
class CoordinateParse:
    label: str
    label_title: str
    coordinates: list[Coordinate] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return bool(self.coordinates)

    def to_dict(self) -> dict[str, Any]:
        return {
            "label_title": self.label_title,
            "coordinates": [c.to_dict() for c in self.coordinates],
        }


def _free(occupied: list[tuple[int, int]], a: int, b: int) -> bool:
    return all(b <= x or a >= y for x, y in occupied)


def parse_coordinates(label: str) -> CoordinateParse:
    """Find GPS-like pairs; ``label_title`` has those spans removed (GPS-only)."""
    from .chainage import title_from_orig_spans

    raw = label or ""
    if not raw:
        return CoordinateParse(label=raw, label_title="")

    found: list[Coordinate] = []

    # 1) Role pairs: (LS: 10.9730N, 124.9025E)
    role_pat = re.compile(
        rf"(?i)\(\s*(LS|RS)\s*:\s*"
        rf"({_DEC})\s*{_DEG}?\s*({_HEM_NS_TOK})\s*,\s*"
        rf"({_DEC})\s*{_DEG}?\s*({_HEM_EW_TOK})\s*\)"
    )
    for m in role_pat.finditer(raw):
        if not (_has_ascii_digit(m.group(2)) and _has_ascii_digit(m.group(4))):
            continue
        a = _parse_decimal(m.group(2))
        b = _parse_decimal(m.group(4))
        if a is None or b is None:
            continue
        lat, lon, swapped = _order_lat_lon(
            a, b, a_hem=m.group(3), b_hem=m.group(5)
        )
        found.append(
            Coordinate(
                lat=lat,
                lon=lon,
                raw=m.group(0),
                kind="decimal_hem",
                role=m.group(1).upper(),
                swapped=swapped,
                orig_start=m.start(),
                orig_end=m.end(),
            )
        )

    # 2) DMS in optional parens (standard + OCR-tolerant)
    #    Standard: 11°46'32.00"N
    #    OCR: seconds closed with ° (13.95°N); minutes' dropped (124°5154.78E)
    _MIN = r"[0-9OIlLSBZGsboz|]{1,2}"
    _SEC_CLOSE = rf"(?:[\"″]|{_DEG})?"
    dms_pat = re.compile(
        rf"(?i)\(?\s*"
        rf"({_DEC})\s*{_DEG}\s*({_MIN})\s*['′]\s*"
        rf"({_DEC})\s*{_SEC_CLOSE}\s*({_HEM_NS_TOK})\s*,\s*"
        rf"({_DEC})\s*{_DEG}\s*({_MIN})\s*['′]\s*"
        rf"({_DEC})\s*{_SEC_CLOSE}\s*({_HEM_EW_TOK})\s*\)?"
    )
    for m in dms_pat.finditer(raw):
        lat = _dms_to_decimal(m.group(1), m.group(2), m.group(3), m.group(4))
        lon = _dms_to_decimal(m.group(5), m.group(6), m.group(7), m.group(8))
        if lat is None or lon is None:
            continue
        if not _looks_geo_pair(lat, lon):
            continue
        found.append(
            Coordinate(
                lat=lat,
                lon=lon,
                raw=m.group(0).strip(),
                kind="dms",
                orig_start=m.start(),
                orig_end=m.end(),
            )
        )

    # 2b) DMS with glued minutes+seconds after ° (no apostrophe): 124°5154.78E
    #     First half may be standard or also OCR-tolerant (° as seconds closer).
    dms_glued_pat = re.compile(
        rf"(?i)\(?\s*"
        rf"({_DEC})\s*{_DEG}\s*({_MIN})\s*['′]\s*"
        rf"({_DEC})\s*{_SEC_CLOSE}\s*({_HEM_NS_TOK})\s*,\s*"
        rf"({_DEC})\s*{_DEG}\s*"
        rf"([0-9OIlLSBZGsboz|]{{3,4}}(?:\.[0-9OIlLSBZGsboz|]+)?)\s*"
        rf"({_HEM_EW_TOK})\s*\)?"
    )
    for m in dms_glued_pat.finditer(raw):
        split = _split_glued_mmss(m.group(6))
        if not split:
            continue
        mm, ss = split
        lat = _dms_to_decimal(m.group(1), m.group(2), m.group(3), m.group(4))
        lon = _dms_to_decimal(m.group(5), mm, ss, m.group(7))
        if lat is None or lon is None:
            continue
        if not _looks_geo_pair(lat, lon):
            continue
        found.append(
            Coordinate(
                lat=lat,
                lon=lon,
                raw=m.group(0).strip(),
                kind="dms",
                orig_start=m.start(),
                orig_end=m.end(),
            )
        )

    # 3) Decimal + hemisphere (with/without degree, optional parens)
    hem_pat = re.compile(
        rf"(?i)\(?\s*"
        rf"({_DEC})\s*{_DEG}?\s*({_HEM_NS_TOK})\s*,\s*"
        rf"({_DEC})\s*{_DEG}?\s*({_HEM_EW_TOK})\s*\)?"
    )
    for m in hem_pat.finditer(raw):
        if not (_has_fraction(m.group(1)) and _has_fraction(m.group(3))):
            continue
        if not (_has_ascii_digit(m.group(1)) and _has_ascii_digit(m.group(3))):
            continue
        a = _parse_decimal(m.group(1))
        b = _parse_decimal(m.group(3))
        if a is None or b is None:
            continue
        # Hemisphere form still needs PH-ish magnitudes
        if not (
            _looks_geo_pair(a, b)
            or (_LAT_LO <= a <= _LAT_HI and 100 <= b <= 140)
            or (_LON_LO <= a <= _LON_HI and _LAT_LO <= b <= _LAT_HI)
        ):
            continue
        lat, lon, swapped = _order_lat_lon(
            a, b, a_hem=m.group(2), b_hem=m.group(4)
        )
        found.append(
            Coordinate(
                lat=lat,
                lon=lon,
                raw=m.group(0).strip(),
                kind="decimal_hem",
                swapped=swapped,
                orig_start=m.start(),
                orig_end=m.end(),
            )
        )

    # 4) Paren pair with optional degree marks: (14.70, 120.92) or (123.80°, 7.98°)
    #    OCR: stray ' after ° and/or space instead of comma — (124.21693°' 8.191074°)
    paren_pat = re.compile(
        rf"\(\s*({_DEC})\s*{_DEG}?\s*['′]?\s*[,;]?\s+({_DEC})\s*{_DEG}?\s*\)"
        rf"|"
        rf"\(\s*({_DEC})\s*{_DEG}?\s*['′]?\s*,\s*({_DEC})\s*{_DEG}?\s*\)"
    )
    for m in paren_pat.finditer(raw):
        if m.group(1) is not None:
            raw_a, raw_b = m.group(1), m.group(2)
        else:
            raw_a, raw_b = m.group(3), m.group(4)
        if not (_has_fraction(raw_a) or _has_fraction(raw_b)):
            continue
        if not (_has_ascii_digit(raw_a) and _has_ascii_digit(raw_b)):
            continue
        a = _parse_decimal(raw_a)
        b = _parse_decimal(raw_b)
        if a is None or b is None:
            continue
        repaired = _repair_ph_pair(a, b)
        if repaired is None:
            continue
        a, b = repaired
        lat, lon, swapped = _order_lat_lon(a, b)
        found.append(
            Coordinate(
                lat=lat,
                lon=lon,
                raw=m.group(0),
                kind="decimal",
                swapped=swapped,
                orig_start=m.start(),
                orig_end=m.end(),
            )
        )

    # 5) Bare trailing pair (no outer parens): ... City 14.593238, 120.983126
    #    or ... Oriental. 8.499076°, 124.660310°
    bare_pat = re.compile(
        rf"(?<![\w.])({_DEC})\s*{_DEG}?\s*,\s*({_DEC})\s*{_DEG}?(?!\s*{_HEM_NS})"
    )
    for m in bare_pat.finditer(raw):
        if not (_has_fraction(m.group(1)) and _has_fraction(m.group(2))):
            continue
        if not (_has_ascii_digit(m.group(1)) and _has_ascii_digit(m.group(2))):
            continue
        a = _parse_decimal(m.group(1))
        b = _parse_decimal(m.group(2))
        if a is None or b is None or not _looks_geo_pair(a, b):
            continue
        lat, lon, swapped = _order_lat_lon(a, b)
        found.append(
            Coordinate(
                lat=lat,
                lon=lon,
                raw=m.group(0).strip(),
                kind="decimal",
                swapped=swapped,
                orig_start=m.start(),
                orig_end=m.end(),
            )
        )

    # 6) Incomplete truncated: (20.448S12°,   or (14.63001 °N, 121.121
    incomplete_pat = re.compile(
        rf"\(\s*({_DEC})\s*{_DEG}?\s*(?:({_HEM_NS_TOK})\s*,\s*({_DEC})?|{_DEG}?\s*,?\s*)$"
    )
    for m in incomplete_pat.finditer(raw):
        a = _parse_decimal(m.group(1))
        b = _parse_decimal(m.group(3)) if m.lastindex and m.lastindex >= 3 else None
        lat = lon = None
        swapped = False
        if a is not None and b is not None:
            lat, lon, swapped = _order_lat_lon(
                a, b, a_hem=m.group(2), b_hem="E" if m.group(2) else None
            )
        elif a is not None:
            if _LAT_LO <= a <= _LAT_HI:
                lat = a
            elif _LON_LO <= a <= _LON_HI:
                lon = a
        found.append(
            Coordinate(
                lat=lat,
                lon=lon,
                raw=m.group(0),
                kind="decimal",
                swapped=swapped,
                incomplete=True,
                orig_start=m.start(),
                orig_end=m.end(),
            )
        )

    # Non-overlapping, prefer longer
    found.sort(key=lambda c: (c.orig_start, -(c.orig_end - c.orig_start)))
    chosen: list[Coordinate] = []
    occupied: list[tuple[int, int]] = []
    for c in found:
        if _free(occupied, c.orig_start, c.orig_end):
            chosen.append(c)
            occupied.append((c.orig_start, c.orig_end))
    chosen.sort(key=lambda c: c.orig_start)

    title = (
        title_from_orig_spans(raw, [(c.orig_start, c.orig_end) for c in chosen])
        if chosen
        else raw.strip()
    )
    return CoordinateParse(label=raw, label_title=title, coordinates=chosen)


def has_coordinate_cue(label: str) -> bool:
    if not label:
        return False
    if re.search(rf"(?i)\b(?:LS|RS)\s*:", label):
        return True
    if re.search(rf"{_DEC}\s*{_DEG}", label):
        return True
    for m in re.finditer(
        rf"(?i)({_DEC})\s*{_DEG}?\s*{_HEM_NS_TOK}\s*,\s*({_DEC})\s*{_DEG}?\s*{_HEM_EW_TOK}",
        label,
    ):
        if _has_ascii_digit(m.group(1)) and _has_ascii_digit(m.group(2)):
            return True
    for m in re.finditer(
        rf"\(\s*({_DEC})\s*{_DEG}?\s*,\s*({_DEC})\s*{_DEG}?\s*\)", label
    ):
        if not (_has_ascii_digit(m.group(1)) and _has_ascii_digit(m.group(2))):
            continue
        a = _parse_decimal(m.group(1))
        b = _parse_decimal(m.group(2))
        if a is not None and b is not None and _looks_geo_pair(a, b):
            return True
    # Bare PH-ish pair
    for m in re.finditer(rf"(?<![\w.])({_DEC})\s*,\s*({_DEC})", label):
        if not (_has_fraction(m.group(1)) and _has_fraction(m.group(2))):
            continue
        if not (_has_ascii_digit(m.group(1)) and _has_ascii_digit(m.group(2))):
            continue
        a = _parse_decimal(m.group(1))
        b = _parse_decimal(m.group(2))
        if a is None or b is None:
            continue
        if _looks_geo_pair(a, b):
            return True
    # Truncated open coord at EOL: (14.6657,   or (121.02
    m = re.search(rf"\(\s*({_DEC})\s*{_DEG}?\s*,?\s*$", label)
    if m and _has_ascii_digit(m.group(1)) and _has_fraction(m.group(1)):
        a = _parse_decimal(m.group(1))
        if a is not None and (
            _LAT_LO <= a <= _LAT_HI or _LON_LO <= a <= _LON_HI
        ):
            return True
    return False


_FIXTURES = [
    (
        "Completion of Dampalit Pumping Station, Malabon City (14.701817, 120.928578)",
        "Completion of Dampalit Pumping Station, Malabon City",
        [(14.701817, 120.928578)],
    ),
    (
        "Barangay Hall, Lala, Lanao del Norte (123.806752°, 7.980467°)",
        "Barangay Hall, Lala, Lanao del Norte",
        [(7.980467, 123.806752)],  # lon,lat input → lat,lon out
    ),
    (
        "Antipolo City (14.631951 °N, 121.232339°E)",
        "Antipolo City",
        [(14.631951, 121.232339)],
    ),
    (
        "Antipolo City (14.S64132°N, 121.176475°E)",
        "Antipolo City",
        [(14.564132, 121.176475)],
    ),
    (
        "Burauen, Leyte (LS: 10.9730N, 124.9025E) (RS: 10.9800N, 124.9100E)",
        "Burauen, Leyte",
        [(10.9730, 124.9025), (10.9800, 124.9100)],
    ),
    (
        "Catbalogan City (11 °46'32.00\"N, 124°53'6.04\"E)",
        "Catbalogan City",
        [(11 + 46 / 60 + 32 / 3600, 124 + 53 / 60 + 6.04 / 3600)],
    ),
]


def _self_check() -> None:
    for label, title, expected in _FIXTURES:
        p = parse_coordinates(label)
        assert p.ok, label
        assert title in p.label_title or p.label_title == title, (p.label_title, title)
        assert len(p.coordinates) == len(expected), (label, p.coordinates)
        for c, (elat, elon) in zip(p.coordinates, expected):
            assert c.lat is not None and abs(c.lat - elat) < 1e-4, (c.lat, elat, label)
            assert c.lon is not None and abs(c.lon - elon) < 1e-4, (c.lon, elon, label)


if __name__ == "__main__":
    _self_check()
    print("gps self-check OK", len(_FIXTURES), "fixtures")
    for label, *_ in _FIXTURES:
        p = parse_coordinates(label)
        print(p.label_title, "=>", [c.to_dict() for c in p.coordinates])
