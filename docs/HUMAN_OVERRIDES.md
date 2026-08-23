# Human overrides and QA dispositions

**Status:** Accepted contract; no active override stage yet  
**Recorded at:** 2026-08-23T08:40:17+08:00

This document defines how reviewed exceptions enter the numbered ETL DAG
without silently rewriting source observations or hiding algorithm defects.

## Core rules

1. A numbered stage never edits another stage's artifacts in place.
2. An active correction is a new immutable DAG node, normally `NNN.90-*`.
3. Downstream nodes declare the exact corrected or uncorrected input they use.
4. The observed value remains available beside the canonical interpretation.
5. A finding that needs no data change is a QA disposition, not an override.
6. Repeated override patterns are algorithm work and must return to the owning
   `NNN.00` transformation with regression fixtures.

## Correction versus disposition

Use a **human override** only when canonical downstream data must differ from
the observed upstream artifact. Typical cases are illegible source text,
damaged source geometry, or a singular source-PDF defect that cannot be
recovered reliably by a general algorithm.

Use a **QA disposition** when the anomaly is understood and acceptable without
changing canonical data—for example, an unreadable decorative footer excluded
from structured content. A disposition explains a finding; it cannot turn a
failed critical gate into a pass without the gate's explicit waiver policy.

## DAG placement

The default human-override insertion is `.90` after the owning major stage:

```text
001.00-paddle-ocr
  └─→ 001.90-ocr-human-overrides

002.10-token-geometry
  └─→ 002.90-geometry-human-overrides

006.00-rows
  └─→ 006.90-row-human-overrides

008.00-hierarchy
  └─→ 008.90-hierarchy-human-overrides
```

Archived `002.00-layout` and `003.00-table-cells` artifacts are not eligible
canonical override targets unless a later ADR explicitly reactivates them.

Slots `.90`–`.99` are reserved for reviewed human intervention. Do not create
an override node until at least one approved override exists. A node consumes
the immutable upstream JSON plus a version-controlled override specification
and produces complete corrected JSON plus local QA:

```text
overrides/001.90-ocr-human-overrides.json
output/<run>/001.00-paddle-ocr/pages/page-0247.json
  ↓ etl/001.90-ocr-human-overrides.py
output/<run>/001.90-ocr-human-overrides/pages/page-0247.json
output/<run>/001.90-ocr-human-overrides/qa/summary.json
output/<run>/001.90-ocr-human-overrides/qa/applications.json
```

Downstream manifests record the exact dependency, such as
`001.90-ocr-human-overrides`; consumers must not search for the highest or
"latest" available insertion automatically.

## Override record

Each record must contain enough evidence to apply narrowly and fail closed:

```json
{
  "override_id": "OCR-0247-001",
  "status": "approved",
  "stage": "001.90-ocr-human-overrides",
  "run_scope": "extraction-smoke",
  "page": 247,
  "target": {
    "kind": "token",
    "id": 184,
    "upstream_artifact_sha256": "<sha256>",
    "observed": {"text": "4?4", "bbox": [100.0, 200.0, 120.0, 210.0]}
  },
  "operation": "replace_text",
  "canonical": {"text": "424"},
  "category": "source_defect",
  "reason": "Middle digit is illegible in the supplied PDF.",
  "evidence": ["source-raster-600dpi", "adjacent-total-reconciliation"],
  "recorded_by": "<reviewer>",
  "recorded_at": "2026-08-23T08:40:17+08:00",
  "reviewed_by": "<reviewer>",
  "reviewed_at": "2026-08-23T08:40:17+08:00"
}
```

Required controls:

- `override_id` is stable and never reused.
- `status` is `proposed`, `approved`, `retired`, or `rejected`; only approved
  records execute.
- `run_scope`, page, target kind, and target ID constrain application.
- The upstream artifact hash and complete observed value must match. A mismatch
  fails the override instead of guessing a new target.
- `operation` comes from a stage-specific allowlist such as `replace_text`,
  `replace_bbox`, `drop_item`, `add_item`, or `replace_parent`.
- `category`, reason, evidence, author, reviewer, and ISO timestamps are
  mandatory. Evidence must be inspectable, not merely asserted.
- Optional `re_review_when` documents an upstream/model change that invalidates
  the approval.

The corrected artifact retains provenance on the affected object:

```json
{
  "text": "424",
  "observed_text": "4?4",
  "override": {
    "override_id": "OCR-0247-001",
    "category": "source_defect",
    "applied_at": "2026-08-23T08:45:00+08:00"
  }
}
```

## QA disposition record

Dispositions belong to the QA directory of the stage that raised the finding:

```json
{
  "finding_id": "OCR-0247-003",
  "stage": "001.00-paddle-ocr",
  "run": "extraction-smoke",
  "page": 247,
  "disposition": "accepted_source_limitation",
  "reason": "Illegible decorative footer is excluded from structured data.",
  "impact": "none",
  "evidence": ["viewer-review-page-0247"],
  "reviewed_by": "<reviewer>",
  "reviewed_at": "2026-08-23T08:40:17+08:00"
}
```

Allowed dispositions should remain small and explicit: `corrected_upstream`,
`accepted_source_limitation`, `not_reproducible`, `duplicate`, and
`algorithm_issue`. `algorithm_issue` remains actionable and is never a waiver.

## Stage QA and viewer requirements

An override stage's summary records total, applied, skipped, failed, retired,
and rejected counts. Any approved record that does not match exactly fails the
stage. `applications.json` records before/after values and hashes for every
attempt.

The viewer must show observed and corrected layers independently, highlight
overridden objects, expose reason/evidence/reviewer/timestamps, and allow a
reviewer to disable the corrected layer. A corrected view must never make the
original observation inaccessible.

## Promotion back into an algorithm

Review override inventory during every promotion gate. Promote a pattern into
the owning transformation when it recurs or can be expressed safely as a
general rule. Promotion requires:

1. fixtures covering the override cases and non-cases;
2. implementation in the owning `NNN.00` node;
3. a new run proving equivalent or better output;
4. retirement—not deletion—of the superseded override records; and
5. retained QA showing that no retired override was applied.

Historical `fixtures/pdf_patch_reviews.json` is review evidence for rejected v1
PDF fallback mutations. It is not an active override specification and must
not be executed by the v2 DAG.
