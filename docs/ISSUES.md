# Issue history

Living issue and finding log for `paddle_pdf_ocr_v2`. This records problems,
disproven assumptions, deferred scope, and their evidence—not only open tasks.

`Recorded at` uses timezone-aware ISO 8601 through seconds. Existing ISS-001
through ISS-017 use the document timestamp available when this convention was
introduced; future issues capture their creation time directly.

## Status definitions

- **Active:** confirmed and currently actionable.
- **Monitoring:** implemented behavior needs broader evidence.
- **Resolved:** correction is implemented and verified.
- **Disproven:** the prior issue statement was false; retain the correction.
- **Deferred:** valid concern outside current scope.

## Index

| ID | Summary | Severity | Status | Area |
|----|---------|----------|--------|------|
| ISS-001 | V1 orchestration and artifact ownership diverged | High | Resolved in v2 foundation | Pipeline |
| ISS-002 | Carry leaked across gaps and resume skipped hydration | Critical | Resolved in contract | Carry |
| ISS-003 | PDF fallback corrupted five correct Paddle tokens | Critical | Resolved by removal | Extraction |
| ISS-004 | Page 247 was incorrectly documented as a Paddle omission | High | Disproven | Gold data |
| ISS-005 | Simplified cell clustering created a seventh column | High | Resolved | Cells |
| ISS-006 | Raw Paddle result fixtures are not yet retained | Medium | Active | Extraction |
| ISS-007 | Extraction overlays lack broader reviewed dispositions | High | Active | QA |
| ISS-008 | Schema modes have incomplete builder policies | High | Active | Schema |
| ISS-009 | Pre-hierarchy row fidelity is promising but incompletely proven | Critical | Active | Rows |
| ISS-010 | V1 hierarchy parent accuracy is not established | Critical | Active | Hierarchy |
| ISS-011 | PAP hierarchy baseline has missing pages and gap groups | Critical | Active | Hierarchy |
| ISS-012 | V2 resume fingerprint validation is incomplete | High | Active | Pipeline |
| ISS-013 | Cross-volume v2 extraction evidence is not yet burned | High | Active | QA |
| ISS-014 | DSC dictionary quality is outside core migration | Low | Deferred | Domain |
| ISS-015 | Reviewed runs can still be overwritten by name reuse | High | Active | Reproducibility |
| ISS-016 | Cells depended on extract before extract consumed cells | High | Resolved | Pipeline |
| ISS-017 | Multiplexed ETL runner obscured stage ownership | High | Resolved | ETL |
| ISS-018 | Thin ETL adapters obscured single-owner transformations | High | Resolved | ETL |
| ISS-019 | Current Paddle environment cannot execute the OCR smoke | High | Active | Runtime |

## Detailed records

### ISS-001: V1 orchestration and artifact ownership diverged

**Severity:** High  
**Status:** Resolved in v2 foundation  
**Recorded at:** 2026-08-23T08:08:07+08:00  
**Reason:** V2 replaced the conflicting execution paths and duplicated owners
with one package pipeline and one canonical artifact owner per stage.

V1 had overlapping `run_page`, `run_volume`, tier, and subprocess pipeline
paths. It also duplicated structured results inside extraction and final JSON,
allowing stale copies. V2 uses one package `Pipeline`, thin CLI adapters, and
one artifact owner per stage. Full resume invalidation remains ISS-012.

That implementation description records the initial foundation. ADR-014 later
removed the package `Pipeline` and placed transformation ownership in numbered
ETL scripts without reopening the resolved ownership issue.

### ISS-002: Carry leaked across gaps and resume skipped hydration

**Severity:** Critical  
**Status:** Resolved in contract  
**Recorded at:** 2026-08-23T08:08:07+08:00  
**Reason:** Gap leakage is prevented by an explicit contiguous sequence rule;
nonascending commits are rejected and gaps reset state.

V1 sparse execution could reuse carry across omitted pages. One resume path
skipped existing pages without reconstructing outbound carry. V2 `SequenceState`
accepts carry only across `previous + 1`, resets on gaps, and rejects
nonascending commits. Sequential resume hydration still needs end-to-end work
under ISS-012.

### ISS-003: PDF fallback corrupted five correct Paddle tokens

**Severity:** Critical  
**Status:** Resolved by removal  
**Recorded at:** 2026-08-23T08:08:07+08:00  
**Reason:** Source review found zero correct PDF replacements out of all five
historical mutations, so the fallback branch was removed instead of retuned.

V1 made five PDF replacements on 672 pages. Source-raster review rejected all
five: pages 138, 147, 149, 247, and 480. V2 removed PDF-text extraction,
comparison, merge dependencies, viewer controls, and CLI commands under
ADR-002. Historical evidence remains in `fixtures/pdf_patch_reviews.json`.

### ISS-004: Page 247 was incorrectly documented as a Paddle omission

**Severity:** High  
**Status:** Disproven  
**Recorded at:** 2026-08-23T08:08:07+08:00  
**Reason:** A fresh Paddle burn and 600-DPI source-raster review both read
`424`; the historical `474` value came from an unsupported `?`→`7` guess.

Earlier documents claimed Paddle dropped `4?4` and that `?` should normalize to
`7`, producing `474`. Fresh Paddle extracted `424`; a 600-DPI source review
visibly confirmed `424`. The ledger and migration fixture now reject the v1
patch and preserve Paddle output.

### ISS-005: Simplified cell clustering created a seventh column

**Severity:** High  
**Status:** Resolved  
**Recorded at:** 2026-08-23T08:08:07+08:00  
**Reason:** Exact v1/v2 comparison isolated the regression to running-mean
clustering; restoring proven single-link clustering recovered exact grid parity.

The first v2 clustering port compared a new center to the running cluster mean.
Page 13 became 7 columns with fill 0.776. V1 used single-link adjacency. After
restoring it, v1/v2 both produce 125 cells, 23 rows, 6 columns, fill 0.906. A
regression test preserves slow center drift in one column.

### ISS-006: Raw Paddle result fixtures are not yet retained

**Severity:** Medium  
**Status:** Active  
**Recorded at:** 2026-08-23T08:08:07+08:00  
**Reason:** Synthetic payloads validate known contracts but cannot protect
against undocumented Paddle result-shape changes in future package versions.

Synthetic parser tests cover current result shapes, NumPy values, nesting, word
boxes, confidence, and coordinate scaling. They do not retain bounded real
Paddle result payloads. Capture sanitized, compact result fragments for selected
pages so future Paddle upgrades can be tested without GPU inference.

**Exit criteria:** versioned real-result fixtures for OCR, layout, and cells;
parser tests load them; no model internals or page-sized images are embedded.

### ISS-007: Extraction overlays lack broader reviewed dispositions

**Severity:** High  
**Status:** Active  
**Recorded at:** 2026-08-23T08:08:07+08:00  
**Reason:** Successful model execution and complete assignment counts do not
prove that token boxes, chrome labels, and region boundaries are spatially correct.

The six-page smoke runs successfully and the viewer exposes Paddle, layout,
zones, cells, and QA. Runtime success and token counts do not establish spatial
fidelity.

**Exit criteria:** retained reviewed dispositions for pages 8, 13, 115, 195,
247, and 680 covering OCR boxes, chrome, region boundaries, and zones.

### ISS-008: Schema modes have incomplete builder policies

**Severity:** High  
**Status:** Active  
**Recorded at:** 2026-08-23T08:08:07+08:00  
**Reason:** Inference can emit modes that v1 did not build comprehensively;
silent empty output would lose valid source content.

V1 primarily built `lattice` and `amount_anchored` output while inference could
also emit `years`, `prose`, and `passthrough`. V2 must never silently return an
empty structure for an inferred mode.

**Exit criteria:** explicit build/pass-through/unsupported policy and retained
fixtures for every schema mode, including multi-zone pages 8, 108, and 109.

### ISS-009: Pre-hierarchy row fidelity is promising but incompletely proven

**Severity:** Critical  
**Status:** Active  
**Recorded at:** 2026-08-23T08:08:07+08:00  
**Reason:** Prior viewer results are encouraging, but reviewed fixtures and
contiguous-slice evidence are not broad enough to promote the row pipeline.

Prior visual review suggests the pipeline was effective through row data, but
the automated gold is partial. Port the reviewed v1 row algorithms before
redesigning them and test amount attachment, wraps, bullets, order, and boxes.

**Exit criteria:** reviewed migration pages plus contiguous By-OU 13–20 and PAP
115–130 slices; no critical label/amount/wrap regressions; viewer agreement.

### ISS-010: V1 hierarchy parent accuracy is not established

**Severity:** Critical  
**Status:** Active  
**Recorded at:** 2026-08-23T08:08:07+08:00  
**Reason:** Existing confidence counts measure column fit rather than correct
parent relationships, while repeated heuristic revisions left known failures.

Confidence counts were repeatedly described as hierarchy success even though
they measured column fit. Existing snap-radius and greedy-stack revisions move
failures between dense and thin pages.

**Exit criteria:** reviewed parent-edge gold, ambiguous alternatives, table
collation, and a v2 comparison that meets ADR-010 and `PROMOTION_GATES.md`.

### ISS-011: PAP hierarchy baseline has missing pages and gap groups

**Severity:** Critical  
**Status:** Active  
**Recorded at:** 2026-08-23T08:08:07+08:00  
**Reason:** Missing pages and page-gap groups prevent the retained PAP artifact
from establishing complete or production-grade hierarchy behavior.

The retained PAP baseline covers 501/576 pages, leaving 75 missing pages and 36
page-gap issue groups. By-OU covers 96 pages and still reports eight level
jumps. These artifacts cannot prove production hierarchy accuracy.

**Exit criteria:** complete representative contiguous spans first, followed by
full-span coverage accounting before any production claim.

### ISS-012: V2 resume fingerprint validation is incomplete

**Severity:** High  
**Status:** Active  
**Recorded at:** 2026-08-23T08:08:07+08:00  
**Reason:** Atomic writes prevent partial JSON, but reuse can still accept stale
artifacts because complete stage-input fingerprint validation is not implemented.

Atomic persistence and manifests exist, but stage reuse does not yet validate
all producer settings and dependency fingerprints before skipping work.

**Exit criteria:** deterministic per-stage input fingerprints, stale artifact
rejection, interrupted-write tests, and sequential carry hydration tests.

### ISS-013: Cross-volume v2 extraction evidence is not yet burned

**Severity:** High  
**Status:** Active  
**Recorded at:** 2026-08-23T08:08:07+08:00  
**Reason:** All current real v2 burns come from Volume 2B, so cross-volume
generalization remains an assumption rather than retained evidence.

Current real burns are from NEP Volume 2B. Prior fixtures reference Volumes 1,
2A, and 3, but v2 has not produced retained cross-volume extraction QA.

**Exit criteria:** representative pages from all four volumes through Paddle,
layout, assembly, viewer disposition, and retained comparison findings without
volume-specific routing.

### ISS-014: DSC dictionary quality is outside core migration

**Severity:** Low  
**Status:** Deferred  
**Recorded at:** 2026-08-23T08:08:07+08:00  
**Reason:** DSC quality does not block extraction, row fidelity, or hierarchy
migration and would distract from the current critical promotion gates.

DSC enrichment was not a blocking extraction, row, or hierarchy concern. If it
returns, normalization and enrichment must precede DSC and provenance must
remain explicit.

### ISS-015: Reviewed runs can still be overwritten by name reuse

**Severity:** High  
**Status:** Active  
**Recorded at:** 2026-08-23T08:08:07+08:00  
**Reason:** Layer-by-layer comparison preserves history only when the prior run
is retained, but the current CLI can reuse a run name and atomically replace its
stage artifacts.

ADR-011 makes named runs the comparison boundary. That convention is not yet
enforced by a reviewed/locked run state.

**Exit criteria:** a run lifecycle distinguishes working from reviewed/locked;
stage writes refuse a locked run; an explicit derived run records its parent
run and comparable manifest; tests cover accidental overwrite attempts.

### ISS-016: Cells depended on extract before extract consumed cells

**Severity:** High  
**Status:** Resolved  
**Recorded at:** 2026-08-23T08:08:07+08:00  
**Reason:** Numbering the stages exposed a circular dependency that made the
true rebuild order require `extract → cells → extract`.

Stage 003 now consumes immutable Paddle and layout layers and performs region
assignment in memory. Stage 004 consumes the optional cell artifact exactly
once. The graph is now `001 + 002 → optional 003 → 004`.

### ISS-017: Multiplexed ETL runner obscured stage ownership

**Severity:** High  
**Status:** Resolved  
**Recorded at:** 2026-08-23T08:08:07+08:00  
**Reason:** A command switch inside one runner did not mirror numbered artifact
ownership and risked recreating v1's overlapping execution routes.

ADR-012 replaced the multiplexed runner with one numbered executable per
implemented ETL stage. Executables declare their inputs and outputs, share only
CLI/bootstrap utilities, and initially kept transformation logic in the
package. ADR-014 later superseded that ownership detail while preserving the
one-executable decision.

### ISS-018: Thin ETL adapters obscured single-owner transformations

**Severity:** High  
**Status:** Resolved  
**Recorded at:** 2026-08-23T08:32:37+08:00  
**Reason:** The separate `src/` package added navigation and ownership ceremony
without eliminating duplicated OCR or transformation algorithms.

ADR-014 moved each single-owner implementation into its numbered ETL node and
removed the central `Pipeline`. `_shared` now contains only modules with at
least two unchanged numbered consumers. Tests carry matching stage prefixes
and enforce the isolation boundary.

### ISS-019: Current Paddle environment cannot execute the OCR smoke

**Severity:** High  
**Status:** Active  
**Recorded at:** 2026-08-23T09:05:04+08:00  
**Reason:** Paddle 3.3.1 is compiled without CUDA in the current interpreter;
its automatic CPU fallback fails inside the oneDNN executor on both reviewed
smoke pages.

The ordered run `ordered-etl-smoke-20260823T0905+0800` requested `gpu:0`.
Paddle reported that GPU was unavailable, switched to CPU, then raised
`ConvertPirAttribute2RuntimeAttribute not support
[pir::ArrayAttribute<pir::DoubleAttribute>]` on pages 8 and 13. The runner
correctly retained stage/run QA and stopped before stages 002–004.

**Exit criteria:** use a verified CUDA-enabled Paddle environment or a supported
CPU configuration; rerun pages 8 and 13 through stages 001–004; retain a passing
execution record and verify that the reported device matches the requested one.

## Adding or updating an issue

1. Assign the next `ISS-NNN` identifier; never reuse an ID.
2. Record severity, status, evidence, and exit criteria.
3. When resolved, retain the record and add the verifying artifact or test.
4. Link architectural resolutions to `ADR.md`.

*Last updated: 2026-08-23T09:14:46+08:00*
