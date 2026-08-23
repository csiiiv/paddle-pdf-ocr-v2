# V2 viewer contract

The viewer is a pipeline debugger and acceptance surface. It ships alongside
extraction and builders, before hierarchy work begins.

## Reuse from v1

- PDF.js page rendering and calibrated PDF-point overlays.
- Token, line, deterministic geometry, and optional archived-comparison toggles.
- Click artifact/row to highlight its geometry.
- Rows and hierarchy-tree panels.
- Run-scoped QA JSON with page/row navigation.
- Hierarchy confidence and reason badges.

## Correct v2 ownership

The viewer reads immutable stage artifacts directly:

| View | Canonical source |
|------|------------------|
| Paddle tokens | `001.00-paddle-ocr/pages/page-NNNN.json` |
| Token geometry | `002.10-token-geometry/pages/page-NNNN.json` |
| Canonical extraction | `004.00-extract/pages/page-NNNN.json` |
| Rows before hierarchy | `006.00-rows/pages/page-NNNN.json` |
| Final hierarchy | `008.00-hierarchy/pages/page-NNNN.json` |
| Stage findings | `<stage>/qa/*.json` |
| Cross-stage/run findings | `999.00-run-qa/*.json` |

`002.00-layout` regions/zones and `003.00-table-cells` cells are archived A/B
evidence, not canonical sources. The maintained viewer does not load them;
historical comparisons use their retained JSON directly.

It must never repair or merge inconsistent structured copies in JavaScript.
Missing or stale stages are shown as missing/stale with their manifest
fingerprints.

The source PDF is rendered visually, but its embedded text is not extracted or
treated as a pipeline layer.

## Delivery slices

1. **Extraction viewer:** PDF image, Paddle tokens/lines, manifest,
   and QA results.
2. **Geometry viewer:** baseline bands, phrase gaps, phrases, markers, money,
   amount anchors/bands, label indents, separators, alignment fits, and source
   token provenance.
3. **Row viewer:** label/amount boxes, bullets, wraps, schema decision, and raw
   pre-hierarchy row JSON.
4. **Hierarchy workbench:** engine selector, columns/tracks, open carry stack,
   candidate parents, confidence reasons, final tree, and v1/v2 comparison.

## Acceptance rule

No stage is promoted from fixtures to a larger burn solely because automated
tests pass. Its retained QA JSON and representative viewer pages must agree.

## Current implementation

The maintained application is `viewer-react/` (with a production build served
by `scripts/serve_viewer.py`): PDF rendering, canonical Paddle word/line
overlays, page navigation, manifest/raw artifacts, deterministic token-geometry
layers, and retained stage QA. Every derived geometry object links back to its
source tokens and measurements. Defunct model regions and cells are not
fetched or rendered. The Schema panel exposes stage-5 zone decisions, column roles,
confidence, sequence carry, and review reasons. Stage QA opens as a modal
workbench with per-stage tabs, summary metrics, page-result tables, and optional
raw JSON rather than replacing the active inspection panel. The earlier
cell-grid Run Table preview has been removed; a row browser should return only
when canonical stage-006 rows exist. There is no
PDF-text fallback or PDF-text comparison view.

When a human-override insertion exists, the viewer must follow
[`HUMAN_OVERRIDES.md`](HUMAN_OVERRIDES.md): expose observed and corrected
layers separately, highlight affected objects, show provenance and evidence,
and never make the original observation inaccessible.
