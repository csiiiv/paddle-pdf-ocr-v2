# V2 promotion gates

Architectural cleanliness is not sufficient evidence for replacing a working
v1 component. V2 owns the burden of proof.

Human corrections and accepted source limitations are governed by
[`HUMAN_OVERRIDES.md`](HUMAN_OVERRIDES.md). Every promotion reviews the
override inventory for recurring patterns that belong in the owning algorithm;
approved override mismatches are gate failures, not silent skips.

## Default decision

For each stage:

- If v2 is significantly better, promote v2.
- If results are equivalent, prefer the simpler and more observable design.
- If v2 is cleaner but less accurate, keep or port the v1 implementation.
- If evidence is incomplete, the stage remains experimental.

Every comparison is retained under `output/<run>/999.00-run-qa/`; terminal
output or a test count alone cannot promote a stage.

## Comparison unit

Use the same PDF pages and evaluate stage-specific canonical artifacts:

| Stage | Compared evidence |
|-------|-------------------|
| OCR | word coverage, text agreement, confidence, boxes, missed gold text |
| Token geometry | token coverage, baseline bands, phrase splits, marker/money evidence, anchors, overlays |
| Table structure | section bounds, PAP/By-OU classification, row ownership, column roles, cells |
| Schema | reviewed mode, column roles/centers, unsupported-mode diagnostics |
| Rows | labels, wraps, bullets, amount attachment, row boxes, row order |
| Domain | normalized values, anatomy fields, money sums, provenance |
| Hierarchy | reviewed parents, sibling accuracy, orphans, level jumps, carry |

## Required evidence bands

### Gold cases

Small reviewed cases for known failures and important successes. Assertions are
relationship- or field-based, not implementation-specific.

### Representative slices

At least one contiguous By-OU slice and one contiguous PAP slice. This catches
carry and table-scale failures that isolated pages cannot expose.

Current measurement coverage includes the 53-page `token_geometry_spans`
selection. Pages 109–114 form the separate `table_structure_spans` transition
sample for the next stage; inclusion is evidence coverage, not automatic gold.

### Cross-volume smoke

Representative pages from Volumes 1, 2A, 2B, and 3. No new volume-specific
router is allowed merely to pass the smoke.

## Significant improvement criteria

A replacement is significantly better when it meets all hard constraints and
improves at least one primary measure without material regression elsewhere.

### Hard constraints

- No loss of reviewed labels, amounts, wraps, or provenance.
- No increase in critical row-to-amount attachment errors.
- No hierarchy cycles.
- No cross-gap carry leakage.
- Deterministic output for identical manifest fingerprints.
- Every degraded fallback is visible in artifact diagnostics and QA.

### Primary measures

| Area | Promotion signal |
|------|------------------|
| Rows | Fewer reviewed attachment/wrap errors; equal or better amount fidelity |
| Hierarchy | More correct reviewed parent edges and fewer table-scale issues |
| Consistency | Same result through fresh, resume, and CPU-only rerun paths |
| Diagnosability | Failure links to page/row, inputs, decision evidence, and reason |
| Iteration | A stage can rerun without invalidating unrelated expensive stages |

Runtime and storage are secondary unless the fidelity result is tied. A faster
pipeline with worse structure does not win.

### PDF-text scope exclusion

Embedded PDF/Acrobat text is outside the v2 pipeline. There is no PDF-text
layer, merge, comparison gate, or patch stage. Historical review artifacts are
retained only to explain this decision. Reintroducing fallback would require a
new scoped decision and new promotion evidence; it is not part of current work.

## Comparison JSON minimum schema

```json
{
  "gate": "COMPARE_ROWS",
  "run": "pap-gold",
  "baseline": "paddle_pdf_ocr/v1",
  "candidate": "paddle_pdf_ocr_v2",
  "manifest_fingerprints": {},
  "summary": {
    "wins": 0,
    "ties": 0,
    "regressions": 0,
    "critical_regressions": 0,
    "promote": false
  },
  "pages": [],
  "findings": []
}
```

Every finding records page, optional row, metric, baseline value, candidate
value, severity, and a viewer link target.

## Hierarchy-specific promotion

Hierarchy v2 will not become default because its track/decoder model is more
principled. It must beat v1 on reviewed parent relationships and contiguous
table assembly.

Minimum hierarchy report:

- correct/incorrect/unknown reviewed parent edges;
- orphan roots excluding legitimate document roots;
- level jumps greater than one;
- cross-page sibling and parent continuity;
- ambiguous decisions and second-best path margin;
- manual viewer disposition for every critical disagreement.

Until that report recommends promotion, v1 hierarchy remains the baseline and
v2 hierarchy remains selectable but experimental.
