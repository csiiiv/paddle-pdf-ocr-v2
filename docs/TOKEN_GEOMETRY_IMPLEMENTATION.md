# Deterministic token geometry — implementation report

**Status:** Implemented and active as measurement stage `002.10`
**Implementation:** `etl/002.10-token-geometry.py`
**Design companion:** [TOKEN_GEOMETRY_DESIGN.md](TOKEN_GEOMETRY_DESIGN.md)
**Validation fixture:** `fixtures/migration_gold.json`
**Recorded:** 2026-08-23

## Purpose of this report

The design document records the reasoning and intended boundary of deterministic
token geometry. This report records what was actually implemented, the failures
encountered during PDF review, the corrections applied, and the behavior of the
current working model.

The word *model* here means a deterministic geometric model expressed in code
and thresholds. It is not a trained OCR or layout model. PaddleOCR still creates
the source tokens; stage `002.10` deterministically derives measurements from the
retained token text and bounding boxes.

Whitespace is measured in representative character-width units, not relative
to other observed gaps. A leftmost standalone token of 12 or more digits is
separated from following label text by an explicit program-code boundary even
when its gap is narrower than the normal 9 pt / three-character-space rule. It
is classified as `code_candidate` and excluded from label-indent evidence. This
prevents program codes from becoming money phrases or contaminating downstream
label text while retaining source provenance.

## Final pipeline position

The active extraction sequence is now:

```text
001.00 Paddle OCR
  └──→ 002.10 Token Geometry → 002.20 Table Structure
```

The retired model layout/cells and fallback extract/schema stages are archived
under `etl/archive/`. The maintained viewer and active DAG do not load them.

Token geometry is measurement-only. It does not yet classify PAP versus By-OU,
own wrapped lines, construct rows, materialize cells, or assign semantic
hierarchy. Those decisions belong to the planned deterministic table-structure
stage.

Each non-marker, non-code phrase retains a skew-corrected measurement relative
to the page's rightmost recurring amount anchor. Label and mixed-text phrases
use their left edge; money phrases use their right edge. If recurring evidence
is unavailable, the rightmost singleton amount anchor is retained as a
provisional reference. These distances support downstream amount-slot and
hierarchy clustering without assigning semantic roles in stage `002.10`.

Text-like phrases are further tagged as `main_text_candidate` when they are the
leftmost eligible label phrase on a band containing amount anchors. Other
text-like phrases remain `wrapped_text_candidate`. Stage `002.20` applies an
explicit reviewed layout span to the repaired `002.11` geometry: By-OU rows
wrap upward and end at a main-text boundary; PAP rows wrap downward and begin
at a main-text boundary. Pages not covered by a reviewed layout span remain
classified for review.

Row boundaries reuse the main phrase's existing baseline-band segment. They do
not reconstruct horizontal geometry from anchor distance or borrow the amount
column's drift slope. Anchor-relative distance remains evidence for hierarchy
and page-level column clustering only.

Baseline bands are produced with a bootstrap. A conservative raw-bottom pass
first seeks wide, low-residual slope observations. If strict support is
insufficient, a relaxed short-span estimate seeds a second clustering pass;
the result is then re-estimated with the strict full-span acceptance test. The
accepted robust slope normalizes token bottoms to the page midpoint before
final clustering.
Adjacent corrected bands may be reconciled only when their token boxes do not
overlap horizontally and their combined fitted baseline has low error. Raw
bottoms, corrected bottoms, slope support, MAD, confidence, and reconciliation
counts remain in the artifact.

Stage `002.11-token-geometry-repair` is a separate, auditable insertion. It
detects money phrases not claimed by any main label and walks downward only
through claims that contradict the page's supported baseline convention. An
orphan amount replaces the contradicted claim, the evicted amount continues
the walk, and an unclaimed text candidate must absorb the tail. Only closed
chains are applied; healthy claims are never stolen and open chains are
reported for review.

Applied repairs update label/amount relations, promote absorbing labels,
transfer amount phrase membership to the partner label's band, refit affected
bands, and rebuild separator and fit candidates. Every page receives an
independent `002.11` artifact with a `pairing_repair` audit record; `002.10`
remains immutable and rerunning the repair cannot preserve stale edits.

## Source OCR configuration

Stage `001.00` rasterizes each PDF page at 200 DPI and sends the RGB raster to
PaddleOCR 3.7.0 using PP-OCRv6 medium detection and recognition models. It does
not consume the PDF's embedded OCR text layer.

The reviewed detector configuration explicitly sets:

```text
text_det_box_thresh = 0.55
return_word_box = true
document orientation classification = false
document unwarping = false
text-line orientation = false
```

The threshold is explicit because leaving it unset uses the PaddleX OCR
pipeline default of `0.60`, not the detector model file's `0.45` value. On page
688, `0.55` recovered three genuine marker detections—`1.`, `2.`, and `e.`—with
no lost detections. Thresholds from `0.55` through `0.30` produced the same three
recoveries on that page. At `0.20`, an additional empty, zero-confidence box
appeared, so `0.55` was selected as the most conservative successful setting.

This OCR setting is upstream of deterministic geometry. Given a retained stage
001 artifact, stage `002.10` itself is repeatable; changing OCR settings requires
regenerating both artifacts because token IDs and boxes may change.

## Implemented transformation

### 1. Usable token evidence

The stage consumes non-empty Paddle tokens with bounding boxes. It retains the
original token indices as canonical source IDs and never mutates the upstream
artifact.

Page-level robust measurements include:

- median token height;
- median visible-character width;
- estimated ordinary inter-word space width;
- baseline tolerance bounded between `1.25 pt` and `3.0 pt`.

Character width and space width are kept separate. An early implementation used
character width as a proxy for spaces and over-split page 11. The correction
estimates spaces from ordinary adjacent token gaps within Paddle source lines,
using robust page fallbacks when local evidence is insufficient.

### 2. Baseline bands

Tokens are sorted by bbox bottom edge and assigned to derived baseline bands.
Membership uses a running median bottom edge rather than single-link chaining,
preventing gradual vertical drift from joining neighboring printed rows.

Each assignment retains:

- bottom-edge delta;
- vertical overlap with the representative band;
- token-height compatibility;
- aggregate confidence.

Each band retains its bbox, source Paddle line IDs, token IDs, estimated
character/space widths, fitted baseline segment, slope, and residual MAD.
Paddle `line_id` remains provenance only and does not define the band.

### 3. Gaps and phrases

Every adjacent token pair in a band produces a gap observation. Generic phrase
splitting requires both:

```text
gap >= 9 pt
gap >= 3 estimated spaces
```

The physical floor was added after viewer review showed that a relative-only
threshold could turn ordinary spaces into phrase boundaries when local space
width was underestimated. On page 688, introducing the 9 pt floor reduced split
gaps from 67 to 58 while preserving all 17 marker phrases.

A phrase is the contiguous token run between accepted splits. It retains its
token IDs, source OCR line IDs, bbox, text, band ID, lexical observation, and
money confidences.

Current lexical observations are:

- `marker_candidate`;
- `money_candidate`;
- `mixed_candidate`;
- `text_candidate`.

These are evidence labels, not final semantic roles.

### 4. Marker-width compensation

Page 688 exposed unreliable punctuation boxes. For example, the period in `1.`
occupied a much wider recognition box than its visible glyph, reducing the raw
gap to the following label.

For a leading marker shaped like `a.`, `1.`, `a)`, or `1)`, the stage supports
both a one-token marker and a logically combined two-token run such as `1` +
`.`. It retains two gap estimates:

```text
raw_gap = next.x0 - marker_reported_right

compensated_gap = next.x0
                  - marker_first_token.x0
                  - expected_marker_width
```

The expected width uses the local character-width estimate. The stronger of the
raw and compensated physical gaps may establish the marker boundary, but both
measurements and their disagreement remain in QA evidence. A marker split still
requires at least `9 pt`.

On page 688:

| Marker | Raw gap | Compensated gap | Winning evidence |
|---|---:|---:|---|
| `1.` before “Preventive” | 7.20 pt | about 11.3 pt | compensated |
| `a.` before “Asset” | 13.32 pt | about 9.8 pt | raw |

The rule is deliberately limited to a leading marker-shaped run. It is not
applied to arbitrary short tokens, initials, or station syntax.

### 5. Money observations and Total-relative search

Canonical comma-grouped values receive strong lexical money evidence. Bare
numbers remain lower-confidence candidates because they may be years, counts,
codes, station values, or markers.

The first column implementation excluded phrases left of 55% of page width.
Expanded By-OU samples showed that facing-page layouts shift horizontally: the
rule dropped the PS column on pages 18 and 26 even though the same role was
detected on right-shifted page 27.

The working implementation now:

1. finds the rightmost credible amount edge as a provisional Total anchor;
2. opens a search window `0.38 × page_width` to its left;
3. admits money observations inside that Total-relative window;
4. records the Total x-coordinate and left search boundary in diagnostics;
5. defers PS/MOOE/CO/Total role assignment to table structure.

Reviewed results include:

| Page | Observed amount anchors |
|---|---|
| 13 | PS, MOOE, CO, Total |
| 18 | PS, MOOE, Total; CO absent |
| 23 | PS, MOOE, sparse CO, Total |
| 26 | PS, MOOE, Total; CO absent |
| 27 | PS, MOOE, CO, Total |
| 29 | CO, Total |
| 688–690 | one PAP amount column |

### 6. Right-edge drift and skew correction

Constant-x clustering incorrectly split a single amount column on skewed pages.
Page 195 was the strongest example: amount right edges moved from roughly 622 pt
near the top to 634 pt near the bottom.

Horizontal baseline skew and vertical amount-edge drift are measured separately.
The column correction directly estimates shared `dx/dy` from nearby amount
observations likely to belong to the same physical column. It then expresses
each right edge at a common page-center reference y:

```text
corrected_x = raw_x - drift_slope × (center_y - reference_y)
```

Corrected right edges are clustered with a tolerance of at least `6 pt`.
Original boxes are preserved. Viewer guides transform the fitted anchor back
into original page coordinates and therefore appear slanted when the source is
skewed.

Representative results:

| Page | Approximate page-height drift | Result |
|---|---:|---|
| 115 | 0.1 pt | remains vertical |
| 195 | 14.3 pt | three false clusters merged into one |
| 680 | 10.4 pt | two false clusters merged into one |
| 688 | 7.9 pt | two false clusters merged into one |

On page 195, the final 22-member amount anchor has approximately `0.46 pt`
residual MAD.

### 7. Singleton anchors and amount bands

Recurrence is support, not an existence requirement. Every admitted amount can
emit a right-edge anchor. Groups with at least three members receive recurring
support; smaller groups remain provisional and flagged for review.

Each amount-column candidate retains:

- corrected right x at the reference y;
- raw median right x;
- drift slope and residual MAD;
- fitted right-edge segment;
- observed left envelope from the widest amount;
- fitted left-envelope segment;
- member phrase IDs and support type.

The left and right fitted segments form an observed amount band. This is not yet
a semantic cell column or a ruled-table boundary.

### 8. Label indents and separator observations

Non-marker, non-money phrase starts are drift-corrected and clustered into
page-local label-indent anchors. Recurrence indicates local support, while
singletons remain review observations. These anchors work well for PAP
indentation, but they do not establish cross-page hierarchy by themselves.

When a label phrase and amount phrase share a derived baseline band, the stage
also emits a short row-local separator candidate in their horizontal gap. It
retains the label phrase ID, amount phrase ID, band ID, gap width, and guide
segment. It is deliberately marked for review; it is not an asserted cell edge.

### 9. Alignment fits

For each amount-column candidate, the stage records label-to-amount alignment
segments from same-band evidence. Their median slope and slope MAD help inspect
whether label and amount bottoms plausibly share a printed row.

These objects are called *alignment fits* in the viewer. They are diagnostic
evidence for later PAP/By-OU row ownership, not row or cell objects.

## Current artifact contract

The stage writes one JSON artifact per page under:

```text
output/<run>/002.10-token-geometry/pages/page-NNNN.json
```

Top-level measurement collections are:

```json
{
  "algorithm": {},
  "baseline_bands": [],
  "gaps": [],
  "phrases": [],
  "column_candidates": [],
  "label_indent_anchors": [],
  "separator_candidates": [],
  "fit_candidates": [],
  "unassigned_token_ids": [],
  "diagnostics": {}
}
```

The implemented parameter set is:

| Parameter | Value | Purpose |
|---|---:|---|
| `baseline_height_fraction` | 0.22 | Initial bottom-edge tolerance from token height |
| `baseline_tolerance_min_pt` | 1.25 | Lower tolerance bound |
| `baseline_tolerance_max_pt` | 3.0 | Upper tolerance bound |
| `phrase_gap_spaces` | 3.0 | Relative generic phrase boundary |
| `phrase_gap_min_pt` | 9.0 | Physical generic boundary floor |
| `marker_gap_min_pt` | 9.0 | Physical marker boundary floor |
| `column_max_total_offset_fraction` | 0.38 | Total-relative four-column search window |
| `column_min_members` | 3 | Recurring-support threshold |

Algorithm output is stamped as `deterministic_token_geometry`, version 1. Raw
Paddle token IDs remain the traceability boundary throughout the artifact.

## Viewer implementation

`viewer-react` loads token geometry independently of archived model layers and
uses cache-disabled JSON requests. Available geometry toggles include:

- baseline bands;
- gaps;
- phrases;
- markers;
- money observations;
- amount right-edge anchors;
- amount bands;
- label indents;
- label/amount separator candidates;
- alignment fits;
- labels.

The old model overlays are labeled **Archived Layout** and **Archived Cells**.
They are not canonical inputs. Regenerated geometry appears after page refresh
or automatically when live updates are enabled.

## Validation coverage

All declared token-geometry spans in `migration_gold.json` have been processed:

```text
13–18, 23–29,
115–130,
144–146,
176–179,
195–200,
446–452,
680,
688–690
```

This is 53 pages covering:

- complete and sparse By-OU column occupancy;
- facing-page horizontal shifts;
- PAP starts and continuations;
- marker fragments and missed small-glyph recovery;
- deep wrapped labels;
- chainage and station noise;
- page 195 right-edge drift;
- PAP/FAP continuation through pages 688–690.

The latest complete run produced:

- 53/53 Paddle page artifacts;
- 53/53 token-geometry page artifacts;
- zero stage failures;
- 2,398 baseline bands;
- 5,198 phrases;
- 752 marker candidates;
- 80 recurring amount-column candidates.

The repository test suite currently passes 66 ETL tests, plus the React viewer
test and production build.

## Issues encountered and dispositions

| Issue | Evidence | Correction | Disposition |
|---|---|---|---|
| Paddle joined marker and label lines | p688 lines 18, 20, 37 | Ignore Paddle line grouping as structural truth; rebuild bands and phrases from tokens | Resolved for geometry |
| Paddle missed small `e.` marker | p688 | Explicit detector box threshold `0.55` | Recovered upstream |
| Punctuation word box contained excess width | p688 `1.` | Raw plus compensated marker gap from marker left edge | Resolved with retained QA disagreement |
| Character width used as space proxy | p11 over-splitting | Estimate actual ordinary inter-token spaces separately | Resolved |
| Relative gap threshold split ordinary words | p688 | Add 9 pt physical floor | Resolved on reviewed pages |
| Constant-x amount clustering fragmented skewed columns | p195, p680, p688 | Robust shared `dx/dy`, reference-y correction, fitted segments | Resolved on reviewed pages |
| Recurrence rejected one-row columns | singleton PAP/By-OU sections | Emit provisional singleton anchors | Resolved as measurement evidence |
| Absolute page-width cutoff lost shifted PS columns | p18, p26 versus p27 | Search left relative to provisional Total | Resolved on expanded By-OU set |
| “Columns” label implied complete cells | p195 viewer review | Rename to amount right-edge anchors; add amount bands and label indents | Resolved in viewer terminology |
| Model layout/cells could affect canonical output | active 002.00/003.00 dependencies | Remove both from active DAG and make extract ignore their artifacts | Phased out |

## Known limitations and next boundary

The working model is final for the current measurement scope, not for complete
table parsing. Remaining interpretation belongs downstream:

1. segment page evidence into local table sections;
2. classify each section as PAP, By-OU, or review;
3. assign PS/MOOE/CO/Total roles, preserving empty roles;
4. distinguish PAP first-line alignment from By-OU last-line alignment;
5. establish wrap-aware row ownership bands;
6. decide section bottoms without model layout regions;
7. convert reviewed boundaries into cells;
8. infer semantic hierarchy across rows and pages.

The proposed next node is `002.20-table-structure.py`. It should consume stage
002.10 artifacts, preserve every source phrase/token ID, and expose its own
viewer layers. It should not reintroduce model layout proposals as hidden
fallbacks.

The reviewed By-OU start/end and per-page carry boundary are defined separately
in [`BY_OU_TABLE_STRUCTURE_CONTRACT.md`](BY_OU_TABLE_STRUCTURE_CONTRACT.md).
That contract annotates existing geometry IDs; it does not expand the scope of
stage 002.10.

Other limitations to retain in QA:

- bare numeric phrases remain lexically ambiguous;
- a provisional Total anchor can be wrong on an unusual non-table numeric page;
- one shared page drift is an approximation when sections have different local
  distortions;
- label-indent groups are page-local evidence, not semantic levels;
- amount left envelopes depend on observed value widths and are not physical
  ruled boundaries;
- separator candidates are row-local gap observations, not accepted cell edges.
- currency-prefixed values such as p114 `P...` are not yet recognized as money
  phrases; this is a table-structure blocker and must be fixed with a lexical
  regression fixture rather than an ad hoc page rule.

The supplementary `table_structure_spans` fixture group covers pages 105–120.
It spans multiple table forms, especially the By-OU → By-Year transition on
pages 107–108, and continues through performance indicators, the summary
lattice, and PAP startup. It is separate from the 53-page token-geometry
aggregate. Page 114 currently demonstrates the currency-prefix limitation
above.

## Reproduction

Process all fixture token-geometry spans by expanding
`fixtures/migration_gold.json::token_geometry_spans`, then run stages 001 and
002.10 for the resulting pages. The most recent expanded selection is:

```bash
python etl/001.00-paddle-ocr.py \
  --pdf pdfs/NEP-2027-VOLUME-2B_OCR.pdf \
  --pages 13-18,23-29,115-130,144-146,176-179,195-200,446-452,680,688-690 \
  --run NEP-2027-VOLUME-2B_OCR --dpi 200 --device gpu:0

python etl/002.10-token-geometry.py \
  --pdf pdfs/NEP-2027-VOLUME-2B_OCR.pdf \
  --pages 13-18,23-29,115-130,144-146,176-179,195-200,446-452,680,688-690 \
  --run NEP-2027-VOLUME-2B_OCR --dpi 200
```

Review the independent geometry overlays in `viewer-react`, especially pages
18, 23, 26, 27, 29, 195, 680, and 688–690.

Empirical anchor-distance bins and the proposed table-local hierarchy procedure
are documented in
[TABLE_HIERARCHY_BIN_CALIBRATION.md](TABLE_HIERARCHY_BIN_CALIBRATION.md).
