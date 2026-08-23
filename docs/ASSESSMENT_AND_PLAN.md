# V1 assessment and v2 build plan

**Status:** Historical assessment; implementation plan superseded
**Recorded at:** 2026-08-23T08:07:49+08:00  
**Timestamp source:** reconstructed from document modification time  
**Last updated:** 2026-08-23T20:17:55+08:00
**Decision:** Clean sibling project; fresh GPU burns are allowed.

> This document records the plan at project inception. It is not the current
> runbook. The active graph is in [`ETL_DAG.md`](ETL_DAG.md), the implemented
> measurement model is in
> [`TOKEN_GEOMETRY_IMPLEMENTATION.md`](TOKEN_GEOMETRY_IMPLEMENTATION.md), and
> ADR-017 records why model layout/cell stages were retired from the canonical
> DAG.

**Promotion policy:** Architectural purity has no independent value. See
[`PROMOTION_GATES.md`](PROMOTION_GATES.md). V2 replaces a reviewed v1 component
only with retained evidence of material improvement or equivalent fidelity with
substantially better consistency and diagnosability.

**Prior-work authority:** [`PRIOR_WORK_LEDGER.md`](PRIOR_WORK_LEDGER.md) records
settled findings, known failures, exact baselines, and migration cases harvested
from all three predecessor projects. Implementation must consult that ledger and
`fixtures/migration_gold.json` before changing a stage.

**Decision and issue authority:** [`ADR.md`](ADR.md) records accepted design
decisions. [`ISSUES.md`](ISSUES.md) tracks active, resolved, deferred, and
disproven findings with exit criteria.

## Assessment

`paddle_pdf_ocr` contains strong extraction experiments and domain knowledge,
but it accumulated overlapping entry points and artifact conventions faster
than its contracts and plans were updated. Its largest risk is inconsistent
execution: the same pages can receive different carry, resume, persistence, and
QA behavior depending on the script used.

V2 therefore starts from a clean package and output layout. We will reuse
reviewed algorithms and gold expectations, not copy the old tree or guarantee
compatibility with old generated artifacts.

### Settled extraction direction

Paddle OCR is the only text-extraction source in v2. The project is migrating
away from Adobe Acrobat OCR because it is slower and empirically less reliable
on these documents. Native/Acrobat PDF text is out of pipeline scope: it is not
burned, compared, merged, or shown by the viewer. The PDF remains an image
source for rasterization and visual review only.

## What is worth carrying forward

| V1 capability | V2 action |
|---------------|-----------|
| PDF-point coordinate normalization | Reimplement from the small proven helper |
| Paddle OCR parsing with word boxes | Port with captured model-output fixtures |
| Layout regions and chrome filtering | Superseded by deterministic token geometry and planned table sections |
| Table-cell detection and quality fallback | Retained only as archived A/B evidence; deterministic cells are downstream |
| Historical PDF/Paddle patch evidence | Preserve only as archived decision evidence |
| Money clustering and slot assignment | Port as tested pure geometry functions |
| Amount-anchored row bands | Port only with real wrap/attachment fixtures |
| Label anatomy | Port as an isolated domain transform |
| Amount-relative hierarchy coordinate `u` | Preserve as an observation feature |
| Ordered column alignment and ghost-parent evidence | Preserve behind hierarchy v2 |
| QA JSON retained per run | Make part of the canonical pipeline |
| PDF-aligned viewer | Reuse interaction ideas against one structured truth |

### Revised migration judgment: preserve the proven row pipeline

Visual review and existing QA indicate that v1 was generally effective through
row construction: OCR geometry, regions, amount attachment, bullets, wraps,
and row data were inspectable and often correct. The repeated failure and
revision cycle was concentrated in hierarchy inference.

V2 therefore must not rewrite working pre-hierarchy algorithms simply because
the project is new. Each component follows this rule:

1. Reburn representative pages under the clean v2 artifact contract.
2. Compare v1 and v2 in the viewer through row output.
3. Port the reviewed v1 implementation when it passes.
4. Replace only behavior with demonstrated fixture or visual failures.

Hierarchy remains an independently selectable stage. Row output before
hierarchy is retained so multiple hierarchy engines can be compared without
re-running extraction or rebuilding rows.

## What should not be copied

- Four overlapping orchestration routes (`run_page`, `run_volume`, `run_tier`,
  and subprocess `run_pipeline`).
- Structured data duplicated in both `extract/` and `json/`.
- Direct non-atomic artifact writes and marker-only resume decisions.
- Page-local column IDs used as persistent hierarchy identity.
- Greedy row-by-row hierarchy inference and repeated snap-radius tuning.
- Broad exception fallbacks without structured degradation diagnostics.
- Documentation that mixes historical plans with current contracts.

## Confirmed v1 consistency defects

The assessment found these concrete issues; v1 was stabilized only so it remains
a usable reference:

1. `domain_post.py` did not reset carry across page gaps.
2. Its resume path skipped pages without reconstructing outbound carry.
3. Its optional HTML call passed `write_html` arguments in reverse order.
4. Sparse `run_page.py` runs could carry state across omitted pages.
5. Domain rebuilds can leave `extract[].structured` stale relative to canonical
   `json/page-*.json`.

## V2 invariants

1. One package-owned orchestration path; CLI modules are thin adapters.
2. One canonical artifact owner per stage.
3. Every artifact declares version, stage, producer, inputs, and parameters.
4. JSON writes are atomic; resume validates content and dependency fingerprints.
5. Carry exists only inside an explicit ascending contiguous sequence.
6. Sparse page sets start independent sequences unless spans are declared.
7. Every fallback records a diagnostic; no silent fidelity degradation.
8. Every stage has fixture contracts before volume execution.
9. QA scripts always retain JSON results inside the run and the viewer consumes
   those same files.
10. A test count is never presented as extraction accuracy.
11. Viewer evidence is a required gate for geometry, attachment, and hierarchy;
    QA summaries link to the exact run/page/row being assessed.
12. Pre-hierarchy rows are a persisted boundary, not an incidental intermediate
    mutated in place by hierarchy.
13. V1 remains the component baseline until a retained comparison report meets
    the applicable promotion gate.

## Canonical run layout

```text
output/<run>/
  manifest.json
  000.00-foundation/qa/{tests,summary}.json
  001.00-paddle-ocr/{pages,qa}/
  002.00-layout/{pages,qa}/
  003.00-table-cells/{pages,qa}/
  004.00-extract/{pages,qa}/
  005.00-schema/{pages,qa}/
  006.00-rows/{pages,qa}/
  007.00-domain/{pages,qa}/
  008.00-hierarchy/{pages,qa}/
  009.00-collation/{artifacts,qa}/
  999.00-run-qa/
  carry.json
  viewer.json
```

The `NNN.II-name` prefix is part of the artifact contract. `NNN` supports up
to 999 major pipeline steps; `II` reserves 00–99 insertion slots after a major
step without renumbering later stages. Stage QA lives beside the artifacts it
evaluates. Only cross-stage/run comparisons belong in `999.00-run-qa`.

Named runs are the history boundary. Do not overwrite a reviewed run to compare
algorithm revisions; create a new run with the same page set and diff matching
stage paths. The first differing numbered stage localizes where behavior
changed, while downstream differences show its effects.

Raster caching will be enabled only when measured useful. A raster is a derived
cache, not a source-of-truth artifact.

`006.00-rows/pages/` is the canonical pre-hierarchy structure.
`008.00-hierarchy/pages/` is the final domain and hierarchy result. This
boundary lets the viewer switch between raw rows,
v1 hierarchy, v2 hierarchy, and future candidate engines without contaminating
the row builder's output.

## ETL ownership plan

```text
etl/
  000.00-foundation.py   repository QA and DAG contracts
  001.00-paddle-ocr.py   PDF → canonical Paddle JSON
  002.00-layout.py       PDF → layout-region JSON
  003.00-table-cells.py  upstream JSON + PDF → cell JSON
  004.00-extract.py      upstream JSON → canonical extract JSON
  _shared/               unchanged infrastructure with 2+ node consumers
  tests/                 tests numbered to match their owning DAG node
```

Future schema, row, domain, hierarchy, and collation logic belongs inside its
matching numbered node. Nodes communicate through retained JSON, never Python
imports. See ADR-014.

## Delivery phases and gates

### V2.0 — foundation

- Numbered ETL nodes and colocated isolated tests.
- Artifact store with atomic JSON replacement.
- Explicit contiguous sequence contract (ADR-008); implementation begins with
  the first real sequential consumer rather than living prematurely in shared.
- Manifest and dependency fingerprint contract.
- QA result schema and test-result emitter.

Run `python etl/000.00-foundation.py --run foundation` to persist the current
baseline under `output/foundation/000.00-foundation/qa/`. These files, rather than terminal-only
counts, are the inputs for later QA rollups and viewer panels.

**Gate:** simulated interrupted writes and sparse sequences cannot create valid
resume state or leak carry.

### V2.1 — fresh extraction spine

- Raster at declared DPI.
- Paddle OCR word/line layer.
- Layout regions.
- Deterministic merge into canonical extract JSON.

There is no hybrid merge or PDF-text fallback in v2.

**Gate:** reburn selected pages 8, 13, 115, 195, 247, and 680; retain geometry,
coverage, patch, and overlay QA JSON.

The viewer is delivered during this phase, not after the volume runner. Required
panels are PDF overlay, tokens, lines, regions, zones, cells, raw artifact, and
run QA. Every later stage extends this same tool.

#### V2.1 implementation record (2026-08-23)

Completed and retained:

- One 200-DPI PaddleOCR 3.x engine per run, RGB→BGR input, word boxes, line
  boxes, confidence, PDF-point normalization, parser diagnostics, atomic layers,
  and per-page timing/error records.
- One numbered executable per implemented ETL stage under `etl/`; every script
  owns its transformation end to end. `run_etl.py` invokes the explicit active
  sequence and owns no transformation logic (ADR-014 and ADR-016).
- Six-page V2B smoke at `output/extraction-smoke`: pages 8, 13, 115, 195, 247,
  and 680; Paddle 6/6 with 0 runtime failures in 30.929 seconds. Every page used
  word boxes. This is execution/contract evidence, not OCR fidelity promotion.
- Canonical evidence at
  `output/extraction-smoke/001.00-paddle-ocr/qa/summary.json`; model
  versions and settings in `manifest.json`.
- Extraction viewer defaults to Paddle overlays and exposes Paddle QA.
- Repository contract records at
  `output/foundation/000.00-foundation/qa/{tests,summary}.json`: the retained
  suite currently has 42 passed, 0 failed, and 0 errors. Earlier milestones
  began at 20 and 25 tests; those counts are historical, not current coverage.
- Independent `PP-DocLayout_plus-L` tier at the preserved 0.4 threshold, with
  stable region ordering, chrome classification, assignment diagnostics, and
  retained `002.00-layout/qa/summary.json`. The six-page smoke completed 6/6
  in 10.598 seconds.
- Deterministic CPU assembly at `004.00-extract/pages/page-NNNN.json`: canonical Paddle
  tokens, layout assignment, and explicit zones. It
  completed 6/6 in 0.226 seconds with zero unassigned tokens.
- PDF fallback code and canonical dependencies were removed. Historical review
  records remain archived under `fixtures/` and prior run QA only.
- Selective page-13 cell detection reproduces the retained v1 structural grid:
  125 cells, 23 rows, 6 columns, 0.906 fill ratio, wired model, usable grid.
  A simplified clustering attempt initially produced 7 columns and was rejected;
  the proven single-link clustering behavior was restored and regression-tested.
- All five historical PDF replacements were reviewed with source-raster row
  context and rejected. Paddle was correct on pages 138, 147, 149, 247, and
  480; the PDF layer introduced `!`/`?` corruption. Page 247 reads `424`, not
  v1's inferred `474`. The gold fixture, ledger, and retained patch QA now agree.

Still required before closing V2.1: bounded raw prediction fixtures and broader
visual overlay dispositions.
No extraction or hierarchy promotion has been claimed from the counts above.

### V2.2 — schema and builders

- Explicit policy for every schema mode.
- Port amount-anchored builder against attachment gold cases.
- Port lattice builder against row/amount gold cases.
- Add prose and passthrough behavior rather than silent empty tables.

**Gate:** extract fixtures reproduce reviewed labels, row bands, amount slots,
and provenance within declared tolerances. Viewer row selection must highlight
the corresponding label and amount boxes on the PDF.

### V2.3 — domain and hierarchy

- Isolated idempotent domain transforms.
- Versioned carry.
- Persistent column tracks separated from local columns and semantic levels.
- Joint page-level hierarchy decoding before parent materialization.

**Gate:** reviewed parent relationships and contiguous slice collation beat the
v1 baseline without increasing orphan or level-jump findings.

The viewer must offer pre-hierarchy rows and candidate hierarchy engines as
separate views. Hierarchy confidence, carried parents, column tracks, and the
selected parent path remain visible rather than being flattened into a final
tree only.

### V2.4 — volume and viewer

- One resumable pipeline CLI over package services.
- Per-stage invalidation from manifest fingerprints.
- QA rollup and viewer consuming only canonical v2 JSON.

**Gate:** representative PAP and By-OU slices pass unit, fixture, collate, and
human overlay review before a full-volume burn.

## Output retention

Fresh v2 runs should replace superseded v2 experiments once their QA summaries
are retained. V1 outputs are not copied into v2. They may be removed separately
after reviewed v2 comparison artifacts preserve the evidence needed for
promotion; this plan does not authorize deleting them automatically.
