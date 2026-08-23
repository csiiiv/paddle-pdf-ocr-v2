# Deterministic token geometry — design assessment

> Implementation history, corrections, current artifact fields, validation
> results, and known limitations are recorded in
> [TOKEN_GEOMETRY_IMPLEMENTATION.md](TOKEN_GEOMETRY_IMPLEMENTATION.md).

**Status:** Design assessment; implemented measurement contract documented separately
**Initial scope:** PAP-style tables
**Input:** retained Paddle word tokens and bounding boxes
**Non-goal:** semantic row, bullet, label, hierarchy, or domain extraction

## Why this stage exists

Paddle word tokens are the finest retained OCR evidence. Paddle OCR lines,
LayoutDetection regions, and TableCellsDetection boxes are useful proposals,
but their grouping decisions are opaque and inconsistent on reviewed pages.
For example, page 688 OCR lines 18, 20, and 37 combine list markers with their
labels, while the token boxes retain inspectable marker-to-prose gaps.

The proposed `002.10-token-geometry` stage should derive reproducible spatial
observations from tokens. Given the same token artifact and algorithm version,
it must always produce the same output and explain every grouping decision.

This does not make OCR itself deterministic. Reproducibility begins at the
retained token artifact and requires recording the OCR model/configuration,
raster DPI, geometry algorithm version, and all thresholds.

## Assessment of the proposed primitives

### 1. Visual lines or baseline bands

Proposed rule: tokens with similar bottom edges are on the same line.

This is a strong primary observation, but raw bbox bottom is not a true
typographic baseline. Glyphs, punctuation, OCR padding, font-size changes,
superscripts, and page skew can move it. A robust band should therefore use:

1. bottom-edge proximity as the primary measurement;
2. vertical-overlap and token-height compatibility as supporting evidence;
3. a robust band representative such as the median bottom edge;
4. a non-chaining cluster rule so gradual drift cannot join adjacent rows;
5. optional deskewing only when enough independent anchor pairs support it.

The raw Paddle `line_id` must be retained as comparison provenance, not used as
the derived band's definition.

Band membership should be scored rather than reduced immediately to a binary
claim. A candidate token-to-band score can combine normalized bottom distance,
vertical overlap, height compatibility, and fitted-line residual. The artifact
should retain every component and an aggregate confidence. Hard assignment is
still needed for a usable partition, but low-margin assignments must be flagged.

### 2. Gaps

Every adjacent token pair in a band should retain its measured horizontal gap.

For a leading marker-shaped run such as `a.` or `1.`, retain two measurements:

- the raw gap from the marker's reported right edge to the next token;
- a compensated gap from the marker's left edge, less an expected marker width
  estimated from the local character width.

Paddle word boxes may assign excessive width to tiny punctuation. The two
measurements are evidence rather than corrected token coordinates: phrase
splitting may use the stronger marker-gap signal, while their disagreement is
kept for QA. Apply this only to a leading marker-shaped run followed by text,
not to every one- or two-character token.

Phrase and marker splitting also require a 9 pt physical minimum. Generic
phrase gaps must additionally clear the relative estimated-space threshold.
This prevents a locally underestimated space width from turning ordinary word
spacing into a phrase boundary. A marker may consist of one OCR token (`a.`)
or a logically combined two-token run (`a` + `.`); the latter is measured from
the first token's left edge before expected-width compensation.

Every credible right-side amount emits a `right_edge_anchor`, including a
singleton. Column recurrence raises support but is not required for an anchor
to exist. Estimate shared right-edge drift directly as `dx/dy`, express anchor
x-coordinates at a common page-center reference y, and cluster those corrected
coordinates. Preserve raw x values and render each candidate as its fitted
local segment in original page coordinates. This handles scanned pages whose
amount edge drifts vertically without rewriting token bboxes.

Do not use an absolute fraction of page width to exclude amount columns: facing
pages and source layouts shift horizontally. Treat the rightmost credible
amount edge as a provisional Total anchor, then search left within a bounded
four-column window expressed as an offset from that anchor. The Total anchor,
left search boundary, and admitted observations remain diagnostic evidence;
final PS/MOOE/CO/Total roles belong to downstream table classification.
The artifact must store the measurement even when no split is made.

A single page-wide fixed gap is unlikely to work. Reviewed page 688 shows that
ordinary word gaps and marker-to-label gaps overlap. Paddle word boxes can also
include trailing whitespace in punctuation boxes. Candidate split evidence
should include:

- absolute gap in PDF points;
- gap divided by median token height;
- gap relative to neighboring gaps in the same band;
- token shapes on both sides;
- whether the left run resembles a short marker;
- recurring horizontal starts elsewhere on the page.

Generic phrase splitting should be conservative. Marker fragmentation may use
an explicit, separately reported rule rather than pretending one threshold
explains both word spacing and list gutters.

Gap size should also be expressed in estimated spaces. Estimate character width
from `token_bbox_width / visible_character_count`, using robust height/cohort or
page medians when a token is too short. A boundary at roughly 2–3 spaces is a
useful hypothesis to measure, test, and calibrate—not yet an accepted constant.
Punctuation boxes and OCR boxes containing trailing whitespace require explicit
QA because they can bias both character-width and gap estimates.

### 3. Phrases

A phrase is a contiguous token run on one derived baseline band. It has its own
bbox, token IDs, source OCR line IDs, raw text, normalized preview text, and
the gap decisions that formed it.

Money identification is essential and belongs here as geometric and lexical
evidence. Dividing every phrase immediately into `amount` and `label/title` is
still too binary, so retain these observations first:

- `numeric_candidate`: contains only permitted numeric punctuation;
- `marker_candidate`: short leading numeric/letter punctuation run;
- `text_candidate`: contains letters or other nonnumeric content;
- `mixed_candidate`: contains both money-like and prose material.

Whether a numeric phrase is an amount depends on column repetition and table
context. Bare numbers can instead be years, counts, PREXC values, station data,
page numbers, or list markers. Likewise, non-amount text is not automatically a
label or title.

A canonical comma-grouped phrase can receive high
`money_lexical_confidence` immediately. It becomes a high-confidence
`amount_phrase` when it also belongs to a recurring right-aligned numeric
cluster. Bare numbers remain ambiguous until contextual evidence raises or
lowers their confidence. Money therefore remains a first-class primitive
without calling every numeric phrase money.

The first PAP iteration should recognize canonical comma-grouped values but
retain cases needed later: `P`/`Php` prefixes, parentheses/negative values,
OCR-separated comma groups, and bare numeric values. Recognition must not
normalize destructively.

### 4. Repeated column anchors

Right-aligned numeric phrases can form amount-column candidates by clustering
their right bbox edges. Right edges are more stable than left edges because
amount widths vary.

A recurring right-aligned money cluster can be called an amount-column
candidate. It is not automatically a **PAP** amount column. Evidence includes:

- number of aligned phrases;
- vertical coverage and pitch consistency;
- right-side position relative to page width;
- competing recurring numeric columns;
- proportion of anchors with left-side text on the same baseline;
- header cues only as secondary evidence;
- outliers and missing rows.

One recurring rightmost money cluster with at least three members is sufficient
for an initial PAP candidate, but should be flagged for review until competing
columns and negative controls are evaluated. Several recurring
numeric columns suggest lattice/By-OU, but sparse By-OU pages can expose only
Total and therefore remain ambiguous. The stage should emit candidates and
confidence/evidence, not a final table classification.

### 5. First-line anchors and skew

For a PAP candidate, the rightmost amount phrase supplies a first-line anchor.
Its bottom edge is the baseline proxy. Left-side phrases whose corrected bottom
edges align with it are first-line candidates.

Skew should be estimated across the cluster instead of relying on critical
individual pairs. Each amount contributes candidate same-band left phrases;
their slopes/residuals are aggregated with a robust mean, trimmed fit, or median
regression. Band confidences from section 1 can weight contributions. Report
center, dispersion, residuals, excluded outliers, and every contributing phrase
ID. Both raw and deskewed positions must remain available.

### 6. PAP row bands

The generalized PAP ownership rule is:

> An amount anchor starts a row; following visual bands belong to that row until
> the next amount anchor starts the next row.

This is stronger than nearest-center attachment and preserves deep wraps. The
last row ends at a detected table boundary, next structural section, or page
bottom—with the chosen boundary source recorded.

An amount baseline itself is not the top edge of a rectangular cell because
the glyph extends above it. Keep these concepts separate:

- `first_line_baseline_y`: observed amount-bottom anchor;
- `row_start_y`: top of the first aligned phrase band, with tolerance;
- `row_end_y`: next row's start, structural boundary, or page bottom;
- `row_band_bbox`: derived visualization/ownership interval.

This avoids drawing a cell whose top begins at the text baseline and excludes
the first-line glyphs.

PAP and By-OU have opposite ownership directions and must not share one cell
boundary rule:

- **PAP wraps down:** the amount aligns with the first label line; the row owns
  following bands until the next amount-aligned first line.
- **By-OU wraps up:** the amount/Total aligns with the last label line; the row
  owns preceding bands back to the previous row boundary.

Token geometry should expose the aligned bands and boundaries needed by both.
Schema-specific ownership belongs in a later deterministic table-geometry stage.

### 7. Label-start observations

Left edges of first-line nonnumeric phrases are useful indentation candidates
and can prove recurring page-local indentation groups. They do not alone prove
the final cross-page semantic hierarchy level:

- bullets sit left of prose;
- wraps can extend left or right;
- different semantic levels can share an indent;
- headings and ordinary rows can share an x coordinate;
- hierarchy ultimately depends on cross-row and cross-page relationships.

The geometry stage should emit `prose_start_candidate_x` and
`local_indent_group` clusters. The later hierarchy stage maps these to semantic
levels using inherited state until a defined root resets it.

### 8. Candidate cells

Rectangles formed by row-band and column-boundary intersections are derived
candidate cells, not detected truth. Their contents should be phrase IDs and
token IDs selected by an explicit containment/overlap policy.

Because PAP wraps down and By-OU wraps up, materializing cells should move to a
later deterministic table-geometry stage. `002.10` should stop at token
boundaries, phrase groupings, money/marker evidence, aligned bands, and column
boundaries.

For a later PAP implementation, two candidates are sufficient:

- left content band;
- right amount band.

Empty amount cells, headings between anchored rows, phrases crossing a boundary,
and page-edge truncation must remain visible as diagnostics rather than being
silently forced into a cell.

## Proposed artifact layers

The stage should progress from measurements to increasingly interpretive
candidates:

```text
tokens (input)
  -> baseline_bands
  -> adjacent_gaps
  -> phrase_candidates
  -> numeric/right-edge clusters
  -> first-line anchor candidates
  -> PAP row-band candidates
  -> candidate cells
```

Every object should retain upstream IDs. No layer should replace or mutate the
input token or OCR-line artifact.

Suggested top-level shape:

```json
{
  "page": 688,
  "algorithm": {
    "name": "deterministic_token_geometry",
    "version": 1,
    "parameters": {}
  },
  "baseline_bands": [],
  "gaps": [],
  "phrases": [],
  "column_candidates": [],
  "first_line_anchors": [],
  "row_band_candidates": [],
  "candidate_cells": [],
  "unassigned_token_ids": [],
  "findings": [],
  "diagnostics": {}
}
```

## PAP-first validation set

The proposed `migration_gold.json` ranges are deliberately bounded:

- pages 115–130: PAP start/continuation, hierarchy indents, and marker forms;
- pages 195–200: multi-line project titles and chainage continuations;
- pages 446–452: station noise and deep wraps near the next amount anchor;
- pages 680 and 688: digit-only continuation and glued marker/label OCR lines.

Additional retained candidates containing both markers and multi-line/subtext
labels are pages 144–146, 176–179, and 688–690. These were identified from
prior structured output and require raster confirmation before promotion to
reviewed gold.

Expanded By-OU measurement coverage is pages 13–18 and 23–29. A separate
`table_structure_spans` group covers pages 105–120: late By-OU tables, the
By-OU → By-Year transition on pages 107–108, performance-indicator year/target
tables, the summary lattice, and the start of PAP.

Negative/control pages are also required:

- page 11: prose must not become a PAP table;
- pages 13–14: lattice must not be classified as PAP;
- pages 108–109: mixed schemas must not become one page-wide PAP band;
- page 114: multi-column COE/lattice and currency-prefix handling;
- page 29: sparse lattice with only CO and Total tests false PAP evidence.

## Viewer validation

`viewer-react` is the only UI target for this work. It should independently
toggle and inspect:

- raw tokens;
- Paddle OCR lines;
- derived baseline bands;
- phrases and split gaps;
- amount/right-edge column candidates;
- first-line anchors and skew guides;
- PAP row bands;
- candidate cells.

Selecting any derived object must reveal its source token IDs, source OCR line
IDs, measurements, thresholds, and reasons. A single combined "geometry"
overlay is insufficient for final QA because it prevents isolating the stage
where an incorrect grouping first appears.

## Promotion gates before downstream use

1. Exact deterministic JSON for repeated runs over the same token artifacts.
2. No token loss; every usable token is assigned or explicitly unassigned.
3. Reviewed baseline bands on page 688 marker cases and skewed/wrapped pages.
4. PAP anchor recall and false-positive review on positive and control pages.
5. Deep wraps on page 452 remain in the prior amount-anchored row.
6. Pages 13, 29, 108, 109, and 114 do not receive an unjustified PAP decision.
7. Viewer overlays agree with the PDF raster and inspectable JSON.
8. Threshold sensitivity is reported; small parameter changes must not cause
   unexplained large structural changes.

## Open decisions

Before finalizing the executable contract, decide:

1. calibrate component weights and confidence for bottom distance, overlap,
   height compatibility, and fitted-line residual;
2. test per-line character-width estimates and a 2–3-space split hypothesis,
   including the cohort/page fallback;
3. keep marker and money fragments in token geometry as first-class table
   boundary evidence; final bullet/amount semantics remain downstream;
4. begin with three recurring amount-column members and flag for review;
5. how table/section bottoms are found without model layout regions;
6. materialize candidate cells in a later deterministic table-geometry node;
   `002.10` owns boundaries and groupings;
7. **Resolved:** model line/layout/cell outputs remain optional archived A/B QA
   layers. `002.10` reads only stage 001 tokens, and model layout/cells have
   been removed from the active DAG while bounded evidence is preserved.

Downstream deterministic stages may consume `002.10-token-geometry` as the
canonical measurement layer, but must not treat its candidates as semantic
rows or cells without their own promotion gates.
