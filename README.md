# paddle_pdf_ocr_v2

Clean second-generation NEP PDF extraction and structure pipeline.

V2 is a standalone sibling of `paddle_pdf_ocr`. It owns a single canonical
PDF → OCR evidence → token geometry → table structure → QA flow. GPU artifacts may be
rebuilt; v1 outputs are reference evidence, not a compatibility constraint.

Current status: OCR, deterministic token geometry, table sections, and the
cross-page By-OU and PAP hierarchy explorers plus immediate-child totals
validation are implemented; model layout, legacy cell
detection, extract zones, and schema inference have been phased out of the
canonical DAG. See
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

Only `--pdf-source` is required. Defaults are page `1`, stages `1` through `2.50`,
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
python etl/002.11-token-geometry-repair.py --pdf pdfs/NEP-2027-VOLUME-2B_OCR.pdf --pages 115,688 --run example
python etl/002.20-table-structure.py --pdf pdfs/NEP-2027-VOLUME-2B_OCR.pdf --pages 13,108 --run example
python etl/002.30-by-ou-tree.py --pdf pdfs/NEP-2027-VOLUME-2B_OCR.pdf --pages 13-32 --run example
python etl/002.40-pap-tree.py --pdf pdfs/NEP-2027-VOLUME-2B_OCR.pdf --pages 115-134 --run example
python etl/002.50-tree-totals.py --pdf pdfs/NEP-2027-VOLUME-2B_OCR.pdf --pages 13-134 --run example
```

The retired `002.00-layout`, `003.00-table-cells`, `004.00-extract`, and
`005.00-schema` implementations and tests live under `etl/archive/`. They are
not registered in `run_etl.py` or exposed through the active artifact store.

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
repaired token-geometry overlays for baseline bands, gaps, phrases, markers, money,
amount right anchors, amount bands, label indents, separators, and alignment
fits. It also renders stage-002.20 label/amount column polygons, fit-bounded
row polygons, consolidated alignment boundaries, and reviewed
By-OU table bands from `fixtures/by_ou_table_seeds.json`. Defunct zones,
schema, extract, and model-cell artifacts are not loaded. It supports fit-width, fit-height, and custom zoom;
a draggable document/details split; source filtering; keyboard page navigation;
and linked selection between overlay boxes and inspection tables. Viewer state
is retained in the URL for shareable run/page/panel/zoom links.

The **Tree** tab reads `002.30-by-ou-tree/tree.json` and renders the selected
By-OU pages as a searchable, collapsible hierarchy table. Program codes,
page-local fitted hierarchy centers, cross-page parent carry, subtotals, funding
metadata, source IDs, flags, and the rightmost amount are retained in the JSON.

The **PAP** tab reads `002.40-pap-tree/tree.json` with the same interaction and
source-linking contract. PAP expense classes, sections, outcomes, programs,
regions, offices, projects, and excluded GOP/Loan Proceeds metadata are retained.
The smoke artifact uses pages 115–134; the stage supports the full reviewed
pages 115–690 span.
Selecting a tree row navigates to its source page and highlights its row section.

The **QA** button opens a run-level modal with one tab per implemented stage.
Each tab presents summary metrics and retained page results as a readable table,
with pass/review/fail states and page links back to the PDF. Raw JSON remains
available inside an optional disclosure for debugging.

The **Tree Totals** QA tab reads stage 002.50. Each comparable parent is checked
against the sum of its immediate additive children. Funding children count;
explicit subtotal/grand-total children do not. Checks that reach the final page
of a partial tree are retained as boundary-incomplete unless the children
already exceed the parent, which is a definitive mismatch.

Tokens, Lines, Geometry, Sections, Tree, PAP, Manifest, and Raw inspect canonical
v2 artifacts directly. Stages 002.30 and 002.40 own the By-OU and PAP
table-family hierarchy contracts; stage 002.50 validates their rollups.
Architecture decisions and tracked issues live in
[`docs/ADR.md`](docs/ADR.md) and [`docs/ISSUES.md`](docs/ISSUES.md).
Reviewed source defects, exceptional corrections, and QA waivers follow
[`docs/HUMAN_OVERRIDES.md`](docs/HUMAN_OVERRIDES.md).
