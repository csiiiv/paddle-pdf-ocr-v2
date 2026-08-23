# paddle_pdf_ocr_v2

Clean second-generation NEP PDF extraction and structure pipeline.

V2 is a standalone sibling of `paddle_pdf_ocr`. It owns a single canonical
PDF → layers → extract → structured JSON → QA flow. GPU artifacts may be
rebuilt; v1 outputs are reference evidence, not a compatibility constraint.

Current status: foundation and contract design. See
[`docs/ASSESSMENT_AND_PLAN.md`](docs/ASSESSMENT_AND_PLAN.md).

Before porting or replacing any stage, consult
[`docs/PRIOR_WORK_LEDGER.md`](docs/PRIOR_WORK_LEDGER.md) and the executable
[`fixtures/migration_gold.json`](fixtures/migration_gold.json) inventory.

The first real Paddle extraction smoke is retained under
`output/extraction-smoke/` for pages 8, 13, 115, 195, 247, and 680.

## Development

```bash
cd paddle_pdf_ocr_v2
python -m pytest -q

# Retain named results for QA/viewer consumption:
python etl/000.00-foundation.py --run foundation
```

The retained artifacts are:

- `output/foundation/000.00-foundation/qa/tests.json` — every named test and result;
- `output/foundation/000.00-foundation/qa/summary.json` — foundation totals and environment.

Retained QA uses timezone-aware ISO 8601 `started_at` and `completed_at`
values through seconds, plus monotonic `elapsed_s`. `timestamp_source` tells
whether wall times were captured during the run or reconstructed for legacy
evidence.

## Numbered ETL stages

The canonical graph, node registry, artifact boundaries, invalidation rules,
and extension checklist are documented in
[`docs/ETL_DAG.md`](docs/ETL_DAG.md).

Run an ordered inclusive stage slice with:

```bash
python etl/run_etl.py --pdf-source pdfs/NEP-2027-VOLUME-2B_OCR.pdf \
  --pages "1-2,3,5-7" --start-stage 1 --end-stage 3 --dry-run
```

Page 1 is the first PDF page. `run_etl.py` accepts multiple comma-separated
pages and inclusive ranges, then expands and deduplicates them before invoking
the numbered ETL scripts.

Only `--pdf-source` is required. Defaults are page `1`, stages `1` through `4`,
200 DPI, `gpu:0`, layout score `0.4`, cells score `0.3`, and a unique run name
derived from the PDF stem and current timestamp.

`gpu:0` is the intended production default. The currently active interpreter
does not have a CUDA-enabled Paddle build and its CPU fallback is failing; see
ISS-019 before treating a local extraction burn as runtime validation.

Each implemented transformation has one matching executable in `etl/`:

```bash
python etl/001.00-paddle-ocr.py --pdf pdfs/NEP-2027-VOLUME-2B_OCR.pdf --pages 8,13 --run example
python etl/002.00-layout.py --pdf pdfs/NEP-2027-VOLUME-2B_OCR.pdf --pages 8,13 --run example
python etl/003.00-table-cells.py --pdf pdfs/NEP-2027-VOLUME-2B_OCR.pdf --pages 13 --run example
python etl/004.00-extract.py --pdf pdfs/NEP-2027-VOLUME-2B_OCR.pdf --pages 8,13 --run example
```

Each numbered script owns its transformation end to end: input loading, model
or deterministic transformation, diagnostics, persistence, and stage-local QA.
There is no separate `src/` package or central pipeline service. `_shared/`
contains only infrastructure used unchanged across DAG nodes; numbered nodes
communicate through declared JSON artifacts and never import one another.

## Extraction viewer

```bash
python scripts/serve_viewer.py --run extraction-smoke --page 115
# http://127.0.0.1:8872/paddle_pdf_ocr_v2/viewer/?run=extraction-smoke&page=115&panel=tokens
```

The viewer renders the source PDF with Paddle, layout, and cell overlays. Its
QA panel reads stage-local summaries; Tokens, Lines, Manifest, and Raw inspect
canonical v2 artifacts directly.
Architecture decisions and tracked issues live in
[`docs/ADR.md`](docs/ADR.md) and [`docs/ISSUES.md`](docs/ISSUES.md).
Reviewed source defects, exceptional corrections, and QA waivers follow
[`docs/HUMAN_OVERRIDES.md`](docs/HUMAN_OVERRIDES.md).
