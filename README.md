# paddle_pdf_ocr_v2

Clean second-generation NEP PDF extraction and structure pipeline.

V2 is a standalone sibling of `paddle_pdf_ocr`. It owns a single canonical
PDF → layers → extract → structured JSON → QA flow. GPU artifacts may be
rebuilt; v1 outputs are reference evidence, not a compatibility constraint.

Current status: OCR and deterministic token geometry are implemented; model
layout and cell detection have been phased out of the canonical DAG. Table
structure is the next planned deterministic stage. See
[`docs/TOKEN_GEOMETRY_IMPLEMENTATION.md`](docs/TOKEN_GEOMETRY_IMPLEMENTATION.md)
and [`docs/ETL_DAG.md`](docs/ETL_DAG.md).

Before porting or replacing any stage, consult
[`docs/PRIOR_WORK_LEDGER.md`](docs/PRIOR_WORK_LEDGER.md) and the executable
[`fixtures/migration_gold.json`](fixtures/migration_gold.json) inventory.

The first real Paddle extraction smoke is retained under
`output/extraction-smoke/` for pages 8, 13, 115, 195, 247, and 680.

## Setup

Core package deps are CPU-safe (`pymupdf`, `numpy`, `Pillow`). GPU stages need
two layers:

1. **PaddlePaddle framework** (model runtime) from the CUDA 13 index — not the
   CPU wheel on stock PyPI.
2. **PaddleOCR** (and OpenCV) from PyPI / `.[gpu]`.

```bash
cd paddle_pdf_ocr_v2

# Framework (GTX 1650 / driver CUDA 13 — same recipe as paddle_ocr)
python -m pip install paddlepaddle-gpu==3.3.1 \
  -i https://www.paddlepaddle.org.cn/packages/stable/cu130/

# OCR toolkit + OpenCV
python -m pip install -e '.[gpu]'
# equivalent: python -m pip install -r requirements-gpu.txt

python -c "import paddle; assert paddle.is_compiled_with_cuda()"
```

`paddleocr` 3.7.x is the OCR API; `paddlepaddle-gpu` 3.3.1 is the latest
stable CUDA framework build for Python 3.13 on that index. Installing a
CPU-only `paddlepaddle` into this env recreates ISS-019.

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

python etl/run_etl.py --pdf-source pdfs/NEP-2027-VOLUME-2B_OCR.pdf \
  --pages-json fixtures/migration_gold.json --pages-obj edge_pages --dry-run
```

Page 1 is the first PDF page. `run_etl.py` accepts multiple comma-separated
pages and inclusive ranges, then expands and deduplicates them before invoking
the numbered ETL scripts.

Only `--pdf-source` is required. Defaults are page `1`, stages `1` through `5`,
200 DPI, `gpu:0`, and run name equal to
the PDF stem (reused/overwritten in place). Use an explicit `--run` when you
need a retained comparison copy.

`gpu:0` is the intended production default. Confirm
`paddle.is_compiled_with_cuda()` before treating a local extraction burn as
runtime validation; a CPU-only framework wheel fails OCR (ISS-019).

Each implemented transformation has one matching executable in `etl/`:

```bash
python etl/001.00-paddle-ocr.py --pdf pdfs/NEP-2027-VOLUME-2B_OCR.pdf --pages 8,13 --run example
python etl/002.10-token-geometry.py --pdf pdfs/NEP-2027-VOLUME-2B_OCR.pdf --pages 115,688 --run example
python etl/004.00-extract.py --pdf pdfs/NEP-2027-VOLUME-2B_OCR.pdf --pages 8,13 --run example
python etl/005.00-schema.py --pdf pdfs/NEP-2027-VOLUME-2B_OCR.pdf --pages 8,13 --run example
```

`002.00-layout.py` and `003.00-table-cells.py` are retained only for explicit
archived A/B comparisons. They are inactive in `run_etl.py`, and canonical
extracts never consume their artifacts.

Each numbered script owns its transformation end to end: input loading, model
or deterministic transformation, diagnostics, persistence, and stage-local QA.
There is no separate `src/` package or central pipeline service. `_shared/`
contains only infrastructure used unchanged across DAG nodes; numbered nodes
communicate through declared JSON artifacts and never import one another.

## Extraction viewer

```bash
python scripts/serve_viewer.py --run NEP-2027-VOLUME-2B_OCR --page 115
# http://127.0.0.1:8872/paddle_pdf_ocr_v2/viewer/?run=NEP-2027-VOLUME-2B_OCR&page=115&panel=tokens
```

The run control is a dropdown of `output/` directories that contain `viewer.json`.
Load refreshes that list. Change the selection to switch runs.

The parallel Vite + React implementation is under `viewer-react/`:

```bash
cd viewer-react
npm install
npm run dev
# http://127.0.0.1:5173/?run=NEP-2027-VOLUME-2B_OCR&page=13&panel=tokens
```

For a production build served by the repository helper:

```bash
cd viewer-react && npm run build && cd ..
python scripts/serve_viewer.py --react --run NEP-2027-VOLUME-2B_OCR --page 13
```

The viewer renders the source PDF with token/line and independently toggled
token-geometry overlays for baseline bands, gaps, phrases, markers, money,
amount right anchors, amount bands, label indents, separators, and alignment
fits. Defunct model layout/cell artifacts are not loaded. It supports fit-width, fit-height, and custom zoom;
a draggable document/details split; source filtering; keyboard page navigation;
and linked selection between overlay boxes and inspection tables. Viewer state
is retained in the URL for shareable run/page/panel/zoom links.

The **QA** button opens a run-level modal with one tab per implemented stage.
Each tab presents summary metrics and retained page results as a readable table,
with pass/review/fail states and page links back to the PDF. Raw JSON remains
available inside an optional disclosure for debugging.

Tokens, Lines, Geometry, Zones, Schema, Manifest, and Raw inspect canonical v2 artifacts
directly. Semantic rows, hierarchy trees, and accepted table-cell boundaries
remain deferred until their deterministic stages and contracts exist.
Architecture decisions and tracked issues live in
[`docs/ADR.md`](docs/ADR.md) and [`docs/ISSUES.md`](docs/ISSUES.md).
Reviewed source defects, exceptional corrections, and QA waivers follow
[`docs/HUMAN_OVERRIDES.md`](docs/HUMAN_OVERRIDES.md).
