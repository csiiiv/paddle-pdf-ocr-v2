# Architecture Decision Records

Canonical decision log for `paddle_pdf_ocr_v2`. Accepted records are not
silently rewritten when direction changes; add a superseding ADR instead.

**Evidence order:** reviewed source/viewer → retained representative QA → gold
fixture → ADR → implementation → historical plan prose.

Record times use timezone-aware ISO 8601 to second precision. For ADR-001
through ADR-012, `Recorded at` is the document timestamp available when the
timestamp convention was introduced; it does not claim the decisions occurred
at that exact second. Future records capture their creation time directly.

## Index

| ID | Decision | Status | Recorded at |
|----|----------|--------|------|
| [ADR-001](#adr-001-build-v2-as-a-clean-sibling) | Build v2 as a clean sibling | Accepted | 2026-08-23T08:08:07+08:00 |
| [ADR-002](#adr-002-paddle-is-the-only-text-extraction-source) | Paddle is the only text extraction source | Implemented | 2026-08-23T08:08:07+08:00 |
| [ADR-003](#adr-003-use-200-dpi-for-production-extraction) | Use 200 DPI for production extraction | Accepted | 2026-08-23T08:08:07+08:00 |
| [ADR-004](#adr-004-own-artifacts-by-stage-and-write-json-atomically) | Stage-owned artifacts and atomic JSON | Implemented | 2026-08-23T08:08:07+08:00 |
| [ADR-005](#adr-005-run-gpu-models-as-independent-tier-barriers) | Independent GPU tier barriers | Partially superseded by ADR-017 | 2026-08-23T08:08:07+08:00 |
| [ADR-006](#adr-006-run-table-cell-detection-selectively) | Selective table-cell detection | Superseded by ADR-017 | 2026-08-23T08:08:07+08:00 |
| [ADR-007](#adr-007-retain-run-scoped-qa-and-use-the-viewer-as-a-gate) | Retained QA and viewer gate | Implemented | 2026-08-23T08:08:07+08:00 |
| [ADR-008](#adr-008-carry-exists-only-across-contiguous-pages) | Carry only across contiguous pages | Implemented | 2026-08-23T08:08:07+08:00 |
| [ADR-009](#adr-009-persist-pre-hierarchy-rows-as-a-stage-boundary) | Persist pre-hierarchy rows | Accepted | 2026-08-23T08:08:07+08:00 |
| [ADR-010](#adr-010-replace-v1-hierarchy-inference-but-preserve-its-observations) | Replace hierarchy inference, preserve observations | Accepted | 2026-08-23T08:08:07+08:00 |
| [ADR-011](#adr-011-use-fixed-width-numbered-stage-directories-with-local-qa) | Fixed-width numbered stages with local QA | Implemented | 2026-08-23T08:08:07+08:00 |
| [ADR-012](#adr-012-one-numbered-executable-per-etl-stage) | One numbered executable per ETL stage | Superseded by ADR-014 | 2026-08-23T08:08:07+08:00 |
| [ADR-013](#adr-013-retain-second-precision-timestamps-for-history-and-qa) | Second-precision timestamps for history and QA | Implemented | 2026-08-23T08:11:33+08:00 |
| [ADR-014](#adr-014-numbered-etl-nodes-own-their-transformations) | Numbered ETL nodes own their transformations | Implemented | 2026-08-23T08:32:37+08:00 |
| [ADR-015](#adr-015-model-human-overrides-as-explicit-dag-nodes) | Human overrides are explicit DAG nodes | Accepted | 2026-08-23T08:40:17+08:00 |
| [ADR-016](#adr-016-use-one-explicit-ordered-etl-runner) | One explicit ordered ETL runner | Implemented | 2026-08-23T09:03:30+08:00 |
| [ADR-017](#adr-017-use-deterministic-token-geometry-and-retire-model-layoutcells) | Deterministic token geometry; retire model layout/cells | Implemented | 2026-08-23T20:17:55+08:00 |

## ADR-001: Build v2 as a clean sibling

**Status:** Accepted  
**Recorded at:** 2026-08-23T08:08:07+08:00

### Context

V1 accumulated four orchestration routes, duplicated structured artifacts,
inconsistent resume/carry behavior, and historical plans mixed with current
contracts. Continuing to layer fixes would retain ambiguous ownership.

### Decision

Build `paddle_pdf_ocr_v2` as a standalone sibling package. Port reviewed
algorithms and gold expectations, not the generated tree or orchestration.

### Consequences

- Fresh GPU burns are allowed.
- V1 remains a comparison baseline, not an API compatibility target.
- V2 must prove fidelity through retained gates before replacing a v1 stage.

## ADR-002: Paddle is the only text extraction source

**Status:** Implemented
**Recorded at:** 2026-08-23T08:08:07+08:00

### Context

The project is moving away from Acrobat OCR. V1 produced 359,153 Paddle tokens
and only five PDF-text replacements across 672 pages. Source-raster review
rejected all five replacements: Paddle was correct and PDF text introduced
`!`/`?` corruption, including the erroneous p.247 `424` → `474` path.

### Decision

Use PaddleOCR as the only text source. Do not burn, compare, merge, patch, or
display embedded PDF/Acrobat text. The source PDF is used for rasterization and
visual review only.

### Consequences

- Canonical assembly requires Paddle and layout layers, never `layers/pdf`.
- No PDF-text CLI, viewer control, merge path, or promotion gate exists.
- Historical fallback QA is retained solely as decision evidence.
- Reintroduction requires a new superseding ADR.

## ADR-003: Use 200 DPI for production extraction

**Status:** Accepted  
**Recorded at:** 2026-08-23T08:08:07+08:00

### Context

V1 measurement found that 150 DPI saved roughly 5% runtime but lost rows on
p.480. Extraction fidelity dominates the small speed gain.

### Decision

Use 200 DPI by default. Do not lower it without page-level and row-level
regression evidence.

### Consequences

Optimize through tier reuse and selective models, not reduced raster fidelity.

## ADR-004: Own artifacts by stage and write JSON atomically

**Status:** Implemented  
**Recorded at:** 2026-08-23T08:08:07+08:00

### Context

V1 monolithic and duplicated outputs made invalidation ambiguous. Direct writes
could leave apparently resumable but incomplete JSON.

### Decision

Give each stage one canonical numbered directory under ADR-011. Write JSON
beside its target, flush it, then atomically replace the target. Record artifact
version, stage, producer, manifest settings, and input PDF hash.

### Consequences

- CPU stages can rerun without reburning GPU layers.
- Resume will ultimately validate content and fingerprints, not marker files.
- Structured rows are not duplicated inside extraction artifacts.

## ADR-005: Run GPU models as independent tier barriers

**Status:** Implemented  
**Recorded at:** 2026-08-23T08:08:07+08:00

### Context

The GTX 1650 has 4 GB VRAM. V1 measured approximately 2.7–3.0 GB peak per
model; mixed-model or multi-worker execution risks OOM.

### Decision

Run OCR, layout, and cells as independent tiers with one model instance and one
worker per tier on the 4 GB GPU. Do not keep unrelated GPU models resident.

### Consequences

- The CLI exposes stage commands over one package `Pipeline`.
- Layer artifacts are the barrier and reuse boundary.
- More workers require new measured VRAM evidence.

The first consequence above is historical and was superseded by ADR-014 and
ADR-016: numbered scripts now own transformations and the ordered runner only
launches them as isolated subprocesses.

## ADR-006: Run table-cell detection selectively

**Status:** Implemented  
**Recorded at:** 2026-08-23T08:08:07+08:00

### Context

Cell grids materially help lattice/By-OU tables but add little to most PAP
pages. V1 used wired detection with wireless fallback and line-based text fill.

### Decision

Burn cells only for explicitly selected lattice pages. Use wired-first
detection, wireless fallback for weak detection, grid-quality diagnostics, and
line/geometry fallback when the grid is weak or absent.

### Consequences

- Missing or weak cells never invalidate canonical extraction.
- Page 13 parity is retained: 125 cells, 23 rows, 6 columns, fill 0.906.
- Single-link center clustering is regression-tested after a simplified
  clustering attempt incorrectly produced seven columns.

## ADR-007: Retain run-scoped QA and use the viewer as a gate

**Status:** Implemented  
**Recorded at:** 2026-08-23T08:08:07+08:00

### Context

Terminal-only pass counts were difficult to audit. Geometry and hierarchy can
pass unit tests while remaining visually or structurally wrong.

### Decision

Every gate writes detailed and summary QA JSON into its run. The viewer reads
the same canonical layers and QA and is delivered alongside each stage.
Promotion requires automated evidence plus spatial or tree review.

### Consequences

- Unit counts prove named invariants, not extraction accuracy.
- QA findings must link to the relevant run/page/row.
- Representative slices and collated tables precede full-volume promotion.

## ADR-008: Carry exists only across contiguous pages

**Status:** Implemented  
**Recorded at:** 2026-08-23T08:08:07+08:00

### Context

V1 leaked schema and hierarchy carry across sparse page selections, and resume
could skip pages without reconstructing outbound state.

### Decision

Carry is valid only when `page == previous_page + 1`. Sequential commits must
ascend. Gaps reset state. Resume must hydrate skipped sequential artifacts
before processing a continuation.

### Consequences

- Sparse pages are independent unless the run declares contiguous spans.
- All future schema, stitch, and hierarchy state uses one sequence contract.

## ADR-009: Persist pre-hierarchy rows as a stage boundary

**Status:** Accepted  
**Recorded at:** 2026-08-23T08:08:07+08:00

### Context

V1 generally performed well through row construction, while repeated failures
were concentrated in hierarchy. Mutating rows during hierarchy obscured which
stage introduced an error.

### Decision

Persist canonical pre-hierarchy rows under `rows/`. Final domain/hierarchy
output belongs under `json/`. Hierarchy engines consume rows without rewriting
them.

### Consequences

- Extraction and row work can be promoted independently of hierarchy.
- Multiple hierarchy candidates can be compared without GPU or row rebuilds.
- The viewer must expose pre-hierarchy rows separately from the final tree.

## ADR-010: Replace v1 hierarchy inference but preserve its observations

**Status:** Accepted  
**Recorded at:** 2026-08-23T08:08:07+08:00

### Context

V1 hierarchy underwent repeated snap-radius and clustering revisions. Its
baseline still has eight By-OU level jumps, 1,518 PAP review rows, incomplete
PAP page coverage, and unproven parent accuracy. Page-local columns, persistent
tracks, and semantic levels were conflated.

### Decision

Replace the hierarchy inference engine after the row boundary. Preserve useful
observations: amount-relative coordinate `u`, first-prose-token indent,
monotonic column order, bounded ghost-parent evidence, and amount-frame
rebiasing. Separate local column, persistent track, semantic level, and parent
selection. Decode jointly before materializing parents.

### Consequences

- Fixed snap floors and greedy stack mutation are not carried forward as rules.
- V1 remains the baseline until reviewed parent edges and contiguous collation
  show material improvement without new critical regressions.
- Confidence identifies review work; it is not canonical truth.

## ADR-011: Use fixed-width numbered stage directories with local QA

**Status:** Implemented  
**Recorded at:** 2026-08-23T08:08:07+08:00

### Context

The earlier run layout separated GPU layers but flattened QA into `qa/*.json`,
making ownership and pipeline order less visible. It also hid a dependency
cycle: cells read canonical extract, then extract was rebuilt to include cells.
Layered JSON is most useful for regression localization when matching stages in
separate runs have stable, sortable paths.

### Decision

Use `NNN.II-name` stage directories. `NNN` supports major steps `000`–`999`;
`II` supports insertion slots `00`–`99` without renumbering later stages.

Current order:

```text
000.00-foundation
001.00-paddle-ocr
002.00-layout
003.00-table-cells       optional
004.00-extract
005.00-schema
006.00-rows
007.00-domain
008.00-hierarchy
009.00-collation
999.00-run-qa            cross-stage/run QA only
```

Every stage owns `pages/` (or its stage-specific artifacts) and `qa/`.
`qa/summary.json` evaluates that stage. Cross-stage and cross-run comparisons
belong in `999.00-run-qa`.

Cells consume stages 001 and 002 directly and never stage 004; stage 004 may
consume optional stage 003. This makes the numbered graph acyclic.

Named runs are the comparison boundary. Compare the same numbered stage path
across two runs; the earliest differing stage localizes the source change and
later differences show propagation.

### Consequences

- Lexical directory order is pipeline order.
- Up to 99 inserted steps can follow any major step.
- Manifests declare `run_layout_version` and the exact stage-directory map.
- Reviewed runs must eventually be protected from accidental overwrite
  (ISS-015); until enforced, use a new run name for every retained revision.
- Archived non-pipeline evidence uses `998.00-*` and cannot be confused with an
  active stage.

## ADR-012: One numbered executable per ETL stage

**Status:** Superseded by ADR-014  
**Recorded at:** 2026-08-23T08:08:07+08:00

### Context

A single multiplexed `scripts/run.py` made stage ownership less visible than
the numbered output layout and allowed unrelated execution routes to grow in
v1. Operators need to identify a transformation, its inputs, its outputs, and
its QA from the same stable number.

### Decision

Place ETL executables under `etl/`, with one script per implemented stage and a
filename matching its output directory:

```text
etl/001.00-paddle-ocr.py  → 001.00-paddle-ocr/
etl/002.00-layout.py      → 002.00-layout/
etl/003.00-table-cells.py → 003.00-table-cells/
etl/004.00-extract.py     → 004.00-extract/
```

Each executable declares inputs and outputs in its help text and invokes only
one package-owned stage service. Shared CLI parsing/bootstrap may live in
`etl/_common.py`; transformation logic must remain under `src/`.

Do not create placeholder ETL scripts for unimplemented stages. Add the script
when its input/output contract and QA exist. Non-ETL utilities such as the
viewer server remain under `scripts/`.

### Consequences

- Script order, artifact order, and QA ownership are directly traceable.
- The multiplexed ETL runner and old foundation QA wrapper were removed.
- Tests enumerate implemented ETL scripts and require working `--help` input
  and output contracts for each.
- A future full pipeline driver may orchestrate these services, but cannot own
  alternate transformation logic.

## ADR-013: Retain second-precision timestamps for history and QA

**Status:** Implemented  
**Recorded at:** 2026-08-23T08:11:33+08:00

### Context

Date-only history established ordering only at day granularity. QA retained
durations but could not correlate when stages ran, which made pipeline pace and
artifact provenance harder to audit.

### Decision

Historical records use timezone-aware ISO 8601 timestamps through seconds:
`YYYY-MM-DDTHH:MM:SS+08:00`. New QA summaries and page records retain
`started_at`, `completed_at`, and monotonic `elapsed_s`. Summaries identify
whether timestamps were captured live or reconstructed from older evidence.

Do not invent exact event times for legacy records. A reconstructed timestamp
must state its source; duration remains the authoritative speed measurement.

### Consequences

- Stage chronology can be correlated across the layered pipeline.
- Both wall-clock placement and measured runtime remain available.
- Legacy evidence remains usable without presenting inferred time as observed.

## ADR-014: Numbered ETL nodes own their transformations

**Status:** Implemented  
**Recorded at:** 2026-08-23T08:32:37+08:00

### Context

ADR-012 made numbered scripts visible but left transformation ownership in a
central `src/` package and `Pipeline` class. Understanding one DAG node still
required following a thin adapter through orchestration and single-owner source
modules. The separation removed no actual algorithm duplication.

### Decision

Each numbered ETL script owns its complete transformation: declared input
loading, model or deterministic logic, diagnostics, output persistence, and
stage-local QA. Numbered nodes never import one another; JSON artifacts are the
DAG interfaces. [`ETL_DAG.md`](ETL_DAG.md) is the canonical operational map.

`etl/_shared/` is restricted to code used unchanged by at least two numbered
nodes. Code belongs to its numbered owner by default and is promoted to shared
only with demonstrated multiple consumers. Tests mirror their owning stage as
`test_NNN_II_name.py`; `000.00` owns repository-wide DAG and foundation checks.

### Consequences

- The `src/` package and central `Pipeline` class were removed.
- Opening a numbered script exposes its transformation end to end.
- Structural tests prohibit hidden source orchestration, cross-node imports,
  unnumbered tests, and unsupported `_shared` modules. ETL-focused tests live
  beside their owners under `etl/tests/`.
- Premature sequence-state code was removed; ADR-008 remains the contract and
  will be implemented by the first real sequential consumer.

## ADR-015: Model human overrides as explicit DAG nodes

**Status:** Accepted  
**Recorded at:** 2026-08-23T08:40:17+08:00

### Context

Some singular source-PDF defects may be insignificant, irrecoverable by a
general algorithm, or require a reviewed canonical interpretation. Applying
manual changes inside an existing stage would erase the observed value and
break layer-by-layer provenance.

### Decision

Follow [`HUMAN_OVERRIDES.md`](HUMAN_OVERRIDES.md). Active corrections use
explicit `.90`–`.99` insertion nodes after the owning stage, consume immutable
upstream JSON plus approved version-controlled records, and produce complete
corrected artifacts with local QA. Downstream dependencies are explicit.

Findings that require no data change use QA dispositions instead. Repeated
override patterns return to the owning algorithm and retire their override
records after regression proof.

### Consequences

- No active correction mutates an earlier stage in place.
- Observed and canonical values remain independently inspectable.
- Exact target and artifact hashes prevent overrides drifting onto new data.
- No override node is implemented until an approved real case exists.

## ADR-016: Use one explicit ordered ETL runner

**Status:** Implemented  
**Recorded at:** 2026-08-23T09:03:30+08:00

### Context

The DAG establishes dependencies, but operators need a convenient way to run a
contiguous portion. A declarative plan format and general topology resolver
added machinery beyond the current fixed pipeline.

### Decision

`etl/run_etl.py` owns one explicit `ACTIVE_STAGES` sequence and executes the
inclusive slice selected by `--start-stage` and `--end-stage` for one PDF.
Page selection is one-based throughout and accepts multiple comma-separated
pages and inclusive ranges. The runner expands, deduplicates, and sorts the
selection before invoking numbered scripts as subprocesses. It owns no
transformations. Dry runs create no artifacts; real runs retain execution QA
under `999.00-run-qa`.

Active insertions are explicitly placed in numeric order. Defunct insertions
are removed from the active sequence rather than discovered or selected by a
"latest" rule. Any sequence revision requires downstream rebuild in a new run.

### Consequences

- Normal operation needs one command and no plan file.
- Major bounds include active insertion slots through `.99`.
- Starting mid-pipeline assumes compatible upstream artifacts already exist;
  fingerprint validation remains ISS-012.
- The active tuple and structural tests make execution order visible.

## ADR-017: Use deterministic token geometry and retire model layout/cells

**Status:** Implemented
**Recorded at:** 2026-08-23T20:17:55+08:00

### Context

Reviewed pages showed that model line/layout output could join bullet markers
to labels, omit small markers, and vary in ways that were difficult to explain
or reproduce. Correcting those results required returning to the token text and
fine bounding boxes anyway. PAP and By-OU tables also use different wrap
ownership, so model rectangles did not remove the need for domain-aware,
inspectable geometry.

Stage `002.10-token-geometry` now reconstructs baseline bands and phrases from
stage-001 tokens, preserves gaps and marker/money evidence, estimates page
drift, and emits amount anchors/bands, label indents, separator candidates, and
alignment fits. Its behavior is deterministic and each object retains source
IDs and measurements. The expanded 53-page fixture set and viewer overlays
provided the reviewed implementation evidence.

### Decision

- Make `001.00-paddle-ocr → 002.10-token-geometry → 004.00-extract →
  005.00-schema` the active implemented sequence.
- Remove `002.00-layout` and `003.00-table-cells` from `ACTIVE_STAGES` and from
  canonical extract dependencies.
- Retain their scripts and bounded outputs only as explicitly labeled archived
  A/B evidence.
- Let stage 004 emit a deterministic page fallback zone until a promoted table
  structure stage supplies sections.
- Build semantic sections, PAP/By-OU classification, row ownership, columns,
  and cells in a later deterministic stage; do not hide model fallbacks inside
  it.

### Consequences

- PaddleOCR is the only active model and owns text recognition, not structural
  line or table truth.
- ADR-005 still applies to the remaining GPU OCR tier but no longer mandates
  layout/cell model tiers. ADR-006 is superseded.
- Stage-002.10 candidates are canonical measurement evidence, not semantic
  rows or cells.
- Archived overlays remain useful for diagnosis but cannot change canonical
  output.
- Currency-prefixed amount recognition and deterministic table structure remain
  tracked follow-up work.

## Adding or changing a decision

1. Add the next ADR number and index entry.
2. Use `Proposed`, `Accepted`, `Implemented`, `Rejected`, or `Superseded`.
3. Cite retained evidence or an issue ID.
4. Supersede accepted history rather than silently rewriting it.

*Last updated: 2026-08-23T20:17:55+08:00*
