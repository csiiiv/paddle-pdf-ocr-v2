"""PAP road chainage parse: compact match, digit OCR in tokens, title strip.

See ``docs/chainage.md``. Used by ``project_desc.enrich_project_label``
(chainage before GPS) and ``scripts/apply_project_desc.py``.

**Pre-corrections** (applied before match — crucial for range detection)::

- Bullet / middle-dot / en–em dash / tilde → ASCII ``-`` (range separator)
- Whitespace stripped in the compact shadow
- OCR letter→digit **only inside station numeric bodies** on the match shadow
  (so ``K0lSS`` matches as ``K0155`` without mangling ``South``;
  ``KOOB!`` / ``KOOS!`` → ``K0081`` / ``K0051``; ``?`` → ``7`` in any
  station digit slot, e.g. ``KOOS?``→``K0057``, ``4?4``→``474``)
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any

# Letter → digit inside station / offset bodies only (not whole-label / titles).
# ``!`` is bang-as-1; ``?`` is unrecognized-digit → ``7`` (e.g. ``KOOS?``→``K0057``,
# ``4?4``→``474``). Scoped to stations only.
_LETTER_DIGIT = str.maketrans(
    {
        "O": "0",
        "o": "0",
        "I": "1",
        "l": "1",
        "L": "1",
        "|": "1",
        "!": "1",
        "?": "7",
        "S": "5",
        "s": "5",
        "B": "8",
        "Z": "2",
        "z": "2",
        "G": "6",
    }
)

# Must become ASCII "-" before compact match (range sep). Keep 1:1 length.
_DASH_LIKE_CHARS = frozenset("·•∙●–—−∼~〜")
_DASH_LIKE = str.maketrans({c: "-" for c in _DASH_LIKE_CHARS})

# Bodies allow OCR letters (+ bang / ``?``); normalize after match.
_DIG = r"[0-9OIlLSBZGsboz|!?]"
_DIG_CHARS = frozenset("0123456789OIlLSBZGsboz|!?")
_OFFSET = rf"(?:\(-?{_DIG}+(?:\.{_DIG}+)?\)|{_DIG}+(?:\.{_DIG}+)?)"
_K_TOKEN = rf"K{_DIG}{{2,5}}\+{_OFFSET}"
_STA_TOKEN = rf"STA\.?{_DIG}+\+{_OFFSET}"
_BARE_PLUS = rf"{_DIG}+\+{_OFFSET}"
_C_TOKEN = rf"C[0O]\+{_OFFSET}"
_KM_TOKEN = rf"KM{_DIG}+\+{_OFFSET}"
# Chainage / OCR Chainaqe; integer meters or n+n
_CH_WORD = r"CHAINA(?:GE|QE)"
_CH_INT = rf"{_CH_WORD}{_DIG}+"
_CH_PLUS = rf"{_CH_WORD}{_DIG}+\+{_OFFSET}"

_SEP = r"(?:-|TO)"

# Refuse strip when almost all alphabetic title text was eaten by over-match
_MIN_TITLE_ALPHA = 3


def _fix_digits(s: str) -> str:
    return (s or "").translate(_LETTER_DIGIT)


def preprocess_chainage_text(text: str) -> str:
    """Fold dash-like punctuation so range separators are ASCII ``-``.

    Run **before** compact/match. Does not strip whitespace (that is compact-only)
    and does not letter→digit titles (that would wreck ``South`` / ``Bridge``).
    """
    if not text:
        return ""
    return text.translate(_DASH_LIKE)


def _norm_offset(raw: str) -> str:
    """Normalize `(-337.40)` or `150` / `S00` after digit fix."""
    t = raw.strip()
    if t.startswith("(") and t.endswith(")"):
        inner = _fix_digits(t[1:-1])
        return f"({inner})"
    return _fix_digits(t)


def compact_shadow(text: str) -> tuple[str, list[int]]:
    """Build whitespace-free work string + map compact index → original index.

    Caller should pass ``preprocess_chainage_text`` output so bullets are already ``-``.
    Also folds any remaining dash-like chars to ``-`` (1:1).
    """
    if not text:
        return "", []
    out: list[str] = []
    fmap: list[int] = []
    for i, ch in enumerate(text):
        if ch.isspace():
            continue
        if ch in _DASH_LIKE_CHARS:
            out.append("-")
        else:
            out.append(ch)
        fmap.append(i)
    return "".join(out), fmap


def _digitize_station_bodies(compact: str) -> str:
    """1:1 letter→digit inside station numeric runs for matching only.

    Leaves title letters (``South``, ``Bridge``) untouched. Length preserved so
    compact↔original fmap still applies.
    """
    if not compact:
        return ""
    chars = list(compact)
    n = len(chars)
    i = 0

    def eat_digits(j: int) -> int:
        while j < n and chars[j] in _DIG_CHARS:
            chars[j] = _fix_digits(chars[j])
            j += 1
        return j

    def eat_offset(j: int) -> int:
        if j < n and chars[j] == "(":
            chars[j] = "("
            j += 1
            while j < n and chars[j] != ")":
                if chars[j] in _DIG_CHARS or chars[j] in ".-":
                    if chars[j] in _DIG_CHARS:
                        chars[j] = _fix_digits(chars[j])
                j += 1
            if j < n and chars[j] == ")":
                j += 1
            return j
        return eat_digits(j)

    while i < n:
        # K####+offset
        if chars[i] in "Kk" and i + 1 < n and chars[i + 1] in _DIG_CHARS:
            i += 1
            i = eat_digits(i)
            if i < n and chars[i] == "+":
                i += 1
                i = eat_offset(i)
            continue
        # STA. / STA
        if "".join(chars[i : i + 3]).upper() == "STA":
            i += 3
            if i < n and chars[i] == ".":
                i += 1
            i = eat_digits(i)
            if i < n and chars[i] == "+":
                i += 1
                i = eat_offset(i)
            continue
        # KM
        if (
            "".join(chars[i : i + 2]).upper() == "KM"
            and i + 2 < n
            and chars[i + 2] in _DIG_CHARS
        ):
            i += 2
            i = eat_digits(i)
            if i < n and chars[i] == "+":
                i += 1
                i = eat_offset(i)
            continue
        # C0+ / CO+
        if chars[i] in "Cc" and i + 1 < n and chars[i + 1] in "0Oo":
            chars[i + 1] = "0"
            i += 2
            if i < n and chars[i] == "+":
                i += 1
                i = eat_offset(i)
            continue
        # CHAINAGE / CHAINAQE + digits
        up8 = "".join(chars[i : i + 8]).upper()
        if up8.startswith("CHAINAQE") or up8.startswith("CHAINAGE"):
            i += 8
            i = eat_digits(i)
            if i < n and chars[i] == "+":
                i += 1
                i = eat_offset(i)
            continue
        i += 1
    return "".join(chars)


def _span_to_original(fmap: list[int], start: int, end: int) -> tuple[int, int]:
    """Compact [start, end) → inclusive-ish original [a, b) slice end."""
    if start >= end or start >= len(fmap):
        return 0, 0
    a = fmap[start]
    b = fmap[end - 1] + 1
    return a, b


@dataclass
class ChainageSpan:
    kind: str  # K | Sta | C | KM | Chainage | bare
    start: str  # compact endpoint without kind prefix for K: "0564+150"
    end: str | None = None
    incomplete: bool = False
    orig_start: int = 0
    orig_end: int = 0

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"kind": self.kind, "from": self.start}
        if self.end is not None:
            d["to"] = self.end
        if self.incomplete:
            d["incomplete"] = True
        return d


@dataclass
class ChainageParse:
    label: str
    label_title: str
    chainages: list[ChainageSpan] = field(default_factory=list)
    compact: str = ""

    @property
    def ok(self) -> bool:
        return bool(self.chainages)

    def to_dict(self) -> dict[str, Any]:
        return {
            "label_title": self.label_title,
            "chainages": [c.to_dict() for c in self.chainages],
        }


def _norm_k_token(tok: str) -> str:
    # K0564+150 or K0564+(-337.40) or truncated K0076+
    m = re.match(rf"(?i)K({_DIG}+)\+(.*)$", tok)
    if not m:
        return _fix_digits(tok)
    body = _fix_digits(m.group(1))
    off = (m.group(2) or "").strip()
    if not off:
        return f"{body}+"
    return f"{body}+{_norm_offset(off)}"


def _norm_sta_or_bare(tok: str, *, strip_sta: bool) -> str:
    t = tok
    if strip_sta:
        t = re.sub(r"(?i)^STA\.?", "", t)
    m = re.match(rf"(?i)({_DIG}+)\+(\(.+?\)|.+)$", t)
    if not m:
        return _fix_digits(t)
    return f"{_fix_digits(m.group(1))}+{_norm_offset(m.group(2))}"


def _norm_c_token(tok: str) -> str:
    m = re.match(rf"(?i)C[0O]\+(\(.+?\)|.+)$", tok)
    if not m:
        return "C0+" + _fix_digits(tok.split("+", 1)[-1])
    return f"C0+{_norm_offset(m.group(1))}"


def _norm_km_token(tok: str) -> str:
    m = re.match(rf"(?i)KM({_DIG}+)\+(\(.+?\)|.+)$", tok)
    if not m:
        return _fix_digits(tok)
    return f"{_fix_digits(m.group(1))}+{_norm_offset(m.group(2))}"


def _norm_chainage_endpoint(tok: str) -> str:
    t = re.sub(rf"(?i)^{_CH_WORD}", "", tok)
    if "+" in t:
        left, right = t.split("+", 1)
        return f"{_fix_digits(left)}+{_norm_offset(right)}"
    return _fix_digits(t)


def _find_ranges(compact: str) -> list[tuple[str, int, int, str, str | None, bool]]:
    """Return list of (kind, start, end, from_norm, to_norm|None, incomplete).

    Searches uppercase compact; prefers longer matches; non-overlapping.
    """
    c = compact.upper()
    # Fix Chainaqe → treat as CHAINAGE via pattern already
    candidates: list[tuple[int, int, str, str, str | None, bool]] = []

    def add(
        kind: str,
        a: int,
        b: int,
        left: str,
        right: str | None,
        incomplete: bool = False,
    ) -> None:
        candidates.append((a, b, kind, left, right, incomplete))

    # K range complete / incomplete trailing +
    for m in re.finditer(
        rf"({_K_TOKEN}){_SEP}({_K_TOKEN})", c, flags=re.IGNORECASE
    ):
        add("K", m.start(), m.end(), _norm_k_token(m.group(1)), _norm_k_token(m.group(2)))
    for m in re.finditer(
        rf"({_K_TOKEN}){_SEP}(K{_DIG}{{2,5}}\+?)", c, flags=re.IGNORECASE
    ):
        # incomplete right: K0076+114-K0076+  or -K0076
        right_raw = m.group(2)
        if re.fullmatch(_K_TOKEN, right_raw, flags=re.IGNORECASE):
            continue  # already covered
        add(
            "K",
            m.start(),
            m.end(),
            _norm_k_token(m.group(1)),
            _norm_k_token(right_raw) if "+" in right_raw else _fix_digits(right_raw),
            True,
        )

    # KM range
    for m in re.finditer(
        rf"({_KM_TOKEN}){_SEP}({_KM_TOKEN})", c, flags=re.IGNORECASE
    ):
        add("KM", m.start(), m.end(), _norm_km_token(m.group(1)), _norm_km_token(m.group(2)))

    # Sta range (second may drop Sta.)
    for m in re.finditer(
        rf"({_STA_TOKEN}){_SEP}({_STA_TOKEN}|{_BARE_PLUS})", c, flags=re.IGNORECASE
    ):
        right = m.group(2)
        rnorm = (
            _norm_sta_or_bare(right, strip_sta=True)
            if right.upper().startswith("STA")
            else _norm_sta_or_bare(right, strip_sta=False)
        )
        add(
            "Sta",
            m.start(),
            m.end(),
            _norm_sta_or_bare(m.group(1), strip_sta=True),
            rnorm,
        )

    # C range
    for m in re.finditer(
        rf"({_C_TOKEN}){_SEP}({_C_TOKEN})", c, flags=re.IGNORECASE
    ):
        add("C", m.start(), m.end(), _norm_c_token(m.group(1)), _norm_c_token(m.group(2)))

    # Chainage int or plus ranges; second word may drop
    for m in re.finditer(
        rf"({_CH_PLUS}){_SEP}({_CH_PLUS}|{_BARE_PLUS})", c, flags=re.IGNORECASE
    ):
        right = m.group(2)
        if re.match(rf"(?i){_CH_WORD}", right):
            rnorm = _norm_chainage_endpoint(right)
        else:
            rnorm = _norm_sta_or_bare(right, strip_sta=False)
        add(
            "Chainage",
            m.start(),
            m.end(),
            _norm_chainage_endpoint(m.group(1)),
            rnorm,
        )
    for m in re.finditer(
        rf"({_CH_INT}){_SEP}({_CH_INT}|{_DIG}+)", c, flags=re.IGNORECASE
    ):
        # skip if this span already inside a plus match (rough: require no + in left)
        if "+" in m.group(0):
            continue
        left = _norm_chainage_endpoint(m.group(1))
        right_raw = m.group(2)
        if re.match(rf"(?i){_CH_WORD}", right_raw):
            right = _norm_chainage_endpoint(right_raw)
        else:
            right = _fix_digits(right_raw)
        add("Chainage", m.start(), m.end(), left, right)
    # Incomplete: Chainage 14268 - Chainage
    for m in re.finditer(
        rf"({_CH_INT}|{_CH_PLUS}){_SEP}{_CH_WORD}(?!{_DIG})", c, flags=re.IGNORECASE
    ):
        add(
            "Chainage",
            m.start(),
            m.end(),
            _norm_chainage_endpoint(m.group(1)),
            None,
            True,
        )

    # Singles (only if not covered by a range)
    singles: list[tuple[int, int, str, str, str | None, bool]] = []
    for kind, pat, norm in (
        ("K", _K_TOKEN, _norm_k_token),
        ("KM", _KM_TOKEN, _norm_km_token),
        ("Sta", _STA_TOKEN, lambda t: _norm_sta_or_bare(t, strip_sta=True)),
        ("C", _C_TOKEN, _norm_c_token),
        ("Chainage", _CH_PLUS, _norm_chainage_endpoint),
        ("Chainage", _CH_INT, _norm_chainage_endpoint),
    ):
        for m in re.finditer(pat, c, flags=re.IGNORECASE):
            singles.append((m.start(), m.end(), kind, norm(m.group(0)), None, False))

    # Greedy non-overlapping: sort by start, prefer longer
    candidates.sort(key=lambda t: (t[0], -(t[1] - t[0])))
    chosen: list[tuple[str, int, int, str, str | None, bool]] = []
    occupied: list[tuple[int, int]] = []

    def free(a: int, b: int) -> bool:
        return all(b <= x or a >= y for x, y in occupied)

    for a, b, kind, left, right, incomplete in candidates:
        if free(a, b):
            chosen.append((kind, a, b, left, right, incomplete))
            occupied.append((a, b))

    occupied.sort()
    for a, b, kind, left, right, incomplete in sorted(
        singles, key=lambda t: (t[0], -(t[1] - t[0]))
    ):
        if free(a, b):
            chosen.append((kind, a, b, left, right, incomplete))
            occupied.append((a, b))

    chosen.sort(key=lambda t: t[1])
    return chosen


def title_from_orig_spans(label: str, spans: list[tuple[int, int]]) -> str:
    """Remove ``[start, end)`` original-string spans and tidy separators."""
    if not spans:
        return (label or "").strip()
    parts: list[str] = []
    cursor = 0
    for a, b in sorted(spans, key=lambda s: s[0]):
        if a > cursor:
            parts.append(label[cursor:a])
        cursor = max(cursor, b)
    if cursor < len(label):
        parts.append(label[cursor:])
    title = " ".join(parts)
    title = re.sub(r"\(\s*\)", " ", title)
    # Emptied paren bodies after strip: (,, ), ( ; ), etc.
    title = re.sub(r"\(\s*[,;/\s]*\)", " ", title)
    title = re.sub(r"\s*-\s*,", ",", title)
    title = re.sub(r",\s*-\s*", ", ", title)
    title = re.sub(r"\s*-\s*-\s*", " - ", title)
    title = re.sub(r"(?:\s*,\s*){2,}", ", ", title)
    title = re.sub(r"\s+,", ",", title)
    title = re.sub(r"\s*\.\s*$", "", title)
    title = re.sub(r"\s+", " ", title).strip(" \t,-;/")
    title = re.sub(r"\(\s*$", "", title).strip()
    title = re.sub(r"^\s*\)\s*", "", title).strip()
    title = re.sub(r",\s*$", "", title).strip()
    title = re.sub(r"^\s*,\s*", "", title).strip()
    return title


def _title_from_spans(label: str, spans: list[ChainageSpan]) -> str:
    return title_from_orig_spans(
        label, [(s.orig_start, s.orig_end) for s in spans]
    )


def _title_alpha_count(s: str) -> int:
    return sum(1 for ch in (s or "") if ch.isalpha())


def _strip_was_safe(raw: str, title: str, spans: list[ChainageSpan]) -> bool:
    """Reject over-strip: substantial alphabetic title eaten, almost nothing left."""
    if not spans:
        return True
    raw_a = _title_alpha_count(raw)
    title_a = _title_alpha_count(title)
    if title_a >= _MIN_TITLE_ALPHA:
        return True
    # Label was only stations / punctuation — empty title is fine
    if raw_a < _MIN_TITLE_ALPHA + 2:
        return True
    return False


def parse_chainage(label: str) -> ChainageParse:
    """Split a PAP label into ``label_title`` + structured ``chainages``.

    Pipeline: preprocess (bullet→dash) → compact → digitize station bodies for
    match → find ranges → map spans to original → title strip (with safety gate).
    """
    raw_in = label or ""
    raw = preprocess_chainage_text(raw_in)
    compact, fmap = compact_shadow(raw)
    if not compact:
        return ChainageParse(label=raw_in, label_title=raw_in.strip(), compact="")

    match_c = _digitize_station_bodies(compact)
    found = _find_ranges(match_c)
    spans: list[ChainageSpan] = []
    for kind, a, b, left, right, incomplete in found:
        oa, ob = _span_to_original(fmap, a, b)
        spans.append(
            ChainageSpan(
                kind=kind,
                start=left,
                end=right,
                incomplete=incomplete,
                orig_start=oa,
                orig_end=ob,
            )
        )

    if not spans:
        return ChainageParse(
            label=raw_in, label_title=raw.strip(), chainages=[], compact=compact
        )

    title = _title_from_spans(raw, spans)
    if not _strip_was_safe(raw, title, spans):
        # Over-match: keep raw title, do not emit chainages (fail soft)
        return ChainageParse(
            label=raw_in, label_title=raw.strip(), chainages=[], compact=compact
        )

    return ChainageParse(
        label=raw_in,
        label_title=title,
        chainages=spans,
        compact=compact,
    )


def has_chainage_cue(label: str) -> bool:
    """Cheap gate: compact text looks like a station / chainage clause."""
    raw = preprocess_chainage_text(label or "")
    c, _ = compact_shadow(raw)
    if not c:
        return False
    u = _digitize_station_bodies(c).upper()
    return bool(
        re.search(rf"K{_DIG}{{2,5}}\+", u)
        or re.search(rf"STA\.?{_DIG}+\+", u)
        or re.search(rf"C[0O]\+", u)
        or re.search(rf"KM{_DIG}+\+", u)
        or re.search(rf"{_CH_WORD}{_DIG}", u)
    )


# --- small fixtures for smoke checks ---
_FIXTURES = [
    (
        "Abbut-Conner Rd - K0564 + 150 - K0564 + 200",
        "Abbut-Conner Rd",
        [("K", "0564+150", "0564+200")],
    ),
    (
        "Abbut-Conner Rd • K0564 + 150 - K0564 + 200",
        "Abbut-Conner Rd",
        [("K", "0564+150", "0564+200")],
    ),
    (
        "Abbut-Conner Rd · K0564 + 150 – K0564 + 200",
        "Abbut-Conner Rd",
        [("K", "0564+150", "0564+200")],
    ),
    (
        "AH Lacson Ave - K0010 + (-337.40) - K0010 + 077",
        "AH Lacson Ave",
        [("K", "0010+(-337.40)", "0010+077")],
    ),
    (
        "Abra Cervantes Road - Sta. 17+340 -Sta. 18+200, Abra",
        "Abra Cervantes Road, Abra",
        [("Sta", "17+340", "18+200")],
    ),
    (
        "Flood (C0+000 to C0+220), Caloocan City",
        "Flood, Caloocan City",
        [("C", "C0+000", "C0+220")],
    ),
    (
        "Bypass, Chainage 400 - Chainage 1860, Quezon",
        "Bypass, Quezon",
        [("Chainage", "400", "1860")],
    ),
    (
        "Dumaguete North Rd - K00SS + 400 - K0056 + 303",
        "Dumaguete North Rd",
        [("K", "0055+400", "0056+303")],
    ),
    (
        "Calapan South Rd - K0154 + 1037 - K0lSS + 207",
        "Calapan South Rd",
        [("K", "0154+1037", "0155+207")],
    ),
]


def _self_check() -> None:
    for label, title, expected in _FIXTURES:
        p = parse_chainage(label)
        assert p.ok, label
        got = [(c.kind, c.start, c.end) for c in p.chainages]
        assert got == expected, (label, got, expected)
        # title may vary slightly on comma placement; require expected core
        assert title.split(",")[0].strip() in p.label_title, (p.label_title, title)


if __name__ == "__main__":
    _self_check()
    print("chainage self-check OK", len(_FIXTURES), "fixtures")
    for label, *_ in _FIXTURES:
        p = parse_chainage(label)
        print(p.label_title, "=>", [c.to_dict() for c in p.chainages])
