# Static viewer contract

Freeze the smallest public data shape that `viewer-react-static` may load, and
draw a hard boundary against the pipeline debug viewer.

## Ownership split

| | `viewer-react` | `viewer-react-static` |
|---|---|---|
| Audience | Extractors, QA reviewers | Public readers of extracted documents |
| Data | Canonical `output/<run>/` stage artifacts | Frozen export packs under `static-export/` |
| Trees | By-OU + PAP tree.json (full evidence) | Slim trees (hierarchy + amounts + bbox) |
| PDF | Local `pdfs/` (dev server / `serve_viewer.py`) | Pack-local copy or remote URL |
| Flags | Flags, QA summaries, flag index | **None** — excluded from the export |
| APIs | Vite `/api/runs`, `/api/flag-index`, live reload | Static files only |

The static viewer must never fetch from `output/`, scan directories, or call a
dev-server API. The debug viewer must not gain static-pack awareness. If a
concept crosses both (tree rows, PDF sync), it is ported deliberately.

## Export pack layout

Produced by `scripts/export_static_viewer.py`, read-only over `output/` and
`pdfs/`:

```text
static-export/<doc>/
  manifest.json       # document metadata, tree list, pdf href
  trees/<prefix>-by-operating-units.json
  trees/<prefix>-by-operating-units.csv
  trees/<prefix>-by-pap.json
  trees/<prefix>-by-pap.csv
  pdf/document.pdf    # copied when --pdf copy; absent when a remote URL is set
  index.json          # multi-doc index (one entry per exported doc)
```

Without `--file-prefix`, JSON falls back to short ids (`trees/by-ou.json`,
`trees/pap.json`) and CSV companions are omitted. Prefixes are kebab-cased
(commas/spaces stripped), e.g. `NEP-VOL2B, DPWH` → `nep-vol2b-dpwh`.

`index.json` lives in each pack and at the `static-export/` root. The static
viewer reads exactly one index and exactly one manifest per open document.

## manifest.json

```json
{
  "format": 1,
  "doc": "NEP-2027-VOLUME-2B",
  "title": "National Expenditure Program FY 2027 · Volume 2B",
  "run": "NEP-2027-VOLUME-2B_OCR",
  "generated_at": "2026-08-24T23:00:00+08:00",
  "source": {
    "by_ou_tree": "002.30-by-ou-tree/tree.json",
    "pap_tree": "002.40-pap-tree/tree.json"
  },
  "pages": [13, 14],
  "trees": [
    {
      "id": "by-ou",
      "label": "By Operating Unit",
      "title": "New Appropriations, by Programs / Activities / Projects (Cash-Based), by Operating Units",
      "file": "trees/nep-vol2b-dpwh-by-operating-units.json",
      "csv": "trees/nep-vol2b-dpwh-by-operating-units.csv",
      "schema_format": 2
    },
    {
      "id": "pap",
      "label": "PAP",
      "title": "Programs / Activities / Projects (PAP)",
      "file": "trees/nep-vol2b-dpwh-by-pap.json",
      "csv": "trees/nep-vol2b-dpwh-by-pap.csv",
      "schema_format": 2
    }
  ],
  "pdf": {
    "href": "pdf/document.pdf",
    "remote": null,
    "pages": 722
  }
}
```

Field rules:

- `format` bumps on breaking manifest changes; the viewer refuses unknown
  formats.
- `pages` is the sorted union of pages referenced by exported tree nodes.
  Useful for knowing which pages carry extractable rows; the viewer page
  navigator uses the full PDF page count (`pdf.pages` / PDF.js `numPages`)
  so covers, dividers, and other non-tree pages remain browsable.
- `pdf.href` is pack-relative; `pdf.remote` is an absolute URL alternative.
  Exactly one must be non-null. The viewer tries `href` first, then `remote`.
- `trees[].file` paths are pack-relative. Tree ids are stable (`by-ou`,
  `pap`) and used in share links; public filenames use `--file-prefix`
  kebab-cased with the tree stem (e.g. `nep-vol2b-dpwh-by-operating-units.json`).
- `trees[].csv` is the optional pack-relative public CSV companion. Emitted
  when the exporter runs with `--file-prefix "<volume> <department>"`; absent
  or `null` when disabled. The CSV stem matches the JSON stem.
- `trees[].schema_format` is the downloadable tree schema version (`2` for
  current exports). The viewer accepts formats `1` and `2`.

## Public downloadable data

One JSON + CSV pair per tree, generated from the same slim tree in **document
order**. Filenames are kebab-case with no commas. Tree downloads use
**schema format 2** (`trees[].schema_format` in the manifest).

### By Operating Units (`<prefix>-by-operating-units.{json,csv}`)

**CSV headers**

```text
row_index,id,kind,page,tier_pdf,label,code,parent_id_pdf,parent_id_prexc,depth_pdf,depth_prexc,prexc_identifier,ps,mooe,co,total
```

- One row per tree node except the synthetic `table_root`.
- `row_index` matches the node's position in the JSON `nodes` array (0-based).
- `tier_pdf` is the PDF layout indent depth; `depth_pdf` / `depth_prexc` are
  hop counts from the root along each hierarchy.
- `parent_id_pdf` / `parent_id_prexc` are node ids (blank on roots).
- `prexc_identifier` is digit 7 when `code` is a valid 15-digit PREXC
  (`1` Activity, `2` LFP, `3` FAP); otherwise blank.
- Amount columns are numeric values (blank when the row carries none).

**JSON node** (document order; no `children` array):

```json
{
  "row_index": 42,
  "id": "p28:r8",
  "kind": "program",
  "page": 28,
  "tier_pdf": 1,
  "label": "ASSET PRESERVATION PROGRAM",
  "code": "310100000000000",
  "parent_pdf": "p13:ph13",
  "parent_prexc": "p28:r7",
  "prexc": {
    "prexc_code": "310100000000000",
    "cost_structure": "3",
    "organizational_outcome": "10",
    "program": "10",
    "subprogram": "1",
    "identifier": "1",
    "activity_project": "00000",
    "reserved": "000"
  },
  "bbox": [72.1, 410.2, 520.0, 422.8],
  "amounts": {
    "PS": {"text": "1,234", "value": 1234},
    "Total": {"text": "6,912", "value": 6912}
  },
  "total": null
}
```

Tree envelope adds `format: 2`, `hierarchy_modes: ["pdf", "prexc"]`, and
`default_hierarchy: "prexc"`. There is no ambiguous `parent` field on By-OU
nodes.

### PAP (`<prefix>-by-pap.{json,csv}`)

**CSV headers**

```text
row_index,id,kind,page,tier_pdf,label,code,parent_id,amount,chainages,lat,lon
```

- `chainages` — JSON array of parsed station spans (blank when none).
- `lat` / `lon` — first parsed coordinate when present (blank otherwise).
- Full coordinate lists (including LS/RS pairs) remain in JSON.

**JSON node** adds optional anatomy fields on project rows:

```json
{
  "row_index": 120,
  "label": "Maharlika Highway (LZ)",
  "label_ocr": "Maharlika Highway (LZ) • K0028+150 - K0031+420 …",
  "description": "The program aims to preserve national roads …",
  "chainages": [{"kind": "K", "from": "0028+150", "to": "0031+420"}],
  "coordinates": [{"raw": "(14.672467, 120.942268)", "lat": 14.672467, "lon": 120.942268}]
}
```

- `label` — stripped category title (chainage/GPS removed from display text).
- `label_ocr` — original OCR label before stripping (tooltip in the viewer).
- `description` — program-description prose split from the title when detected.
- `chainages` / `coordinates` — parsed anatomy shown as chips beside the label.

Chainage/GPS stripping runs in stage `002.40-pap-tree` (and at export when
legacy trees lack anatomy). Hierarchy uses the stripped `label`.

### Schema format 1 (legacy)

Format 1 packs remain readable by the viewer. By-OU nodes used `tier` (not
`tier_pdf`), carried `parent` as an alias for `parent_prexc`, and CSV omitted
hierarchy columns. New exports always emit format 2.

## Slim tree shape

```json
{
  "format": 2,
  "id": "pap",
  "title": "Programs / Activities / Projects (PAP)",
  "columns": ["AMOUNT (Php)"],
  "roots": ["root"],
  "nodes": [
    {
      "row_index": 0,
      "id": "root",
      "parent": null,
      "kind": "table_root",
      "tier_pdf": 0,
      "label": "PAP table root",
      "code": null,
      "page": null,
      "bbox": null,
      "amounts": {"AMOUNT (Php)": {"text": "24,685,746,000", "value": 24685746000}},
      "total": null,
      "children": ["n1", "n2"]
    }
  ]
}
```

Node field rules:

- `row_index` is the 0-based document-order index; it matches CSV rows and
  the position in `nodes[]`.
- `id` is an opaque string. By-OU trees use `parent_pdf` (layout indent) and
  `parent_prexc` (code-based indent among existing rows only). The viewer
  toggles these via `hierarchy_modes: ["pdf", "prexc"]`; row order stays
  document order and only indents change. Synthetic PREXC shell nodes are
  omitted from the export pack. PAP trees use `parent` / `children`.
- `tier_pdf` is the PDF layout indent depth (format 1 used the name `tier`).
- `kind` uses the pipeline vocabulary (`table_root`, `section`, `program`,
  `activity`, `region`, `office`, `project`, `funding`, `subtotal`,
  `grand_total`, plus synthetic PREXC shells `prexc_oo`, `prexc_program`,
  `prexc_subprogram`, `prexc_identifier`, …). By-OU coded rows are nested by
  PREXC code after the layout pass (see `docs/prexc_code.md`); uncoded
  region/office children stay under their coded parent.
- `page` is the 1-based source page or `null` for synthetic nodes.
- `bbox` is `[x0, y0, x1, y1]` in PDF points for the node's label row; null
  when the node has no single source row.
- `amounts` keys are column roles (`PS`, `MOOE`, `CO`, `Total`, `AMOUNT (Php)`).
  Each value keeps `text` and `value`; `role`, `phrase_ids`, `token_ids` are
  dropped. `total`, when present, keeps `role`, `text`, and `value`; its
  `role` refers to the same role vocabulary so the viewer renders it in the
  matching column instead of synthesizing a duplicate.
- `columns` is the tree's fixed column vocabulary, left to right. The
  exporter resolves generic `Amount N` ordinals to semantic roles using the
  document's anchor rule: the rightmost data-carrying column on each page is
  `Total`, with `CO`, `MOOE`, `PS` assigned leftward; header text exists only
  on the root page. The PAP tree's single column takes its name from the
  root-page header (`AMOUNT (Php)`).
- `flags`, `tier_fits`, `page_flags`, `calibration`, diagnostics detail, and
  phrase/token provenance are **not** exported. Public artifacts carry no
  review state.

The exporter validates that every non-root node has a `parent`, every parent
id resolves, `children` are consistent with `parent`, and any node with a
`bbox` also has a `page`.

## URL state

Query parameters are retained for shareable links:

```text
?doc=NEP-2027-VOLUME-2B&tree=pap&page=115&node=<id>&zoom=fit|height|custom,<pct>&overlay=show|hide|off
```

- All parameters are optional; the viewer defaults to the first tree, the
  first page, and fit-width zoom.
- `overlay` controls the PDF row boxes: `show` draws them, `hide` keeps them
  clickable but invisible (the default), `off` disables clicking entirely.
- Changing `doc` reloads the manifest; the viewer never rewrites the URL
  silently on load, only on user action.

## Serving

- Local: `npm run dev` with `static-export/` reachable through the dev proxy,
  or `npm run build` then `npm run preview` with the pack beside `dist/`.
- GitHub Pages: the built app plus the pack(s) are published together; the
  viewer resolves paths relative to `import.meta.env.BASE_URL`.
- No `.htaccess`/redirect file is needed; routing is query-based.

## Non-goals

- No flag surface, QA summaries, or review workflow.
- No token/geometry/section overlays.
- No write path anywhere.
- No directory listing dependency (index.json replaces it).
