# React extraction viewer

Vite + React implementation of the v2 viewer. It reads canonical artifacts
directly from the sibling `output/`, `pdfs/`, and `fixtures/` directories and
does not mutate pipeline data.

The maintained geometry workbench exposes independent overlays for Paddle
tokens/lines and deterministic stage-002.10 evidence: baseline bands, gaps,
phrases, marker and money phrases, amount right anchors, amount bands, label
indents, separator candidates, and alignment fits. Stage-002.20 header polygons,
label/amount column polygons, fit-bounded row polygons, intersecting cell polygons,
consolidated boundaries, and reviewed By-OU bands are independently toggleable
under **Sections**.
Defunct zones, schema, extract, and model-cell artifacts are not loaded by this
application. Selection links overlays to their source IDs and
measurements; run/page/panel/zoom state is shareable through the URL.

```bash
cd viewer-react
npm install
npm run dev
# http://127.0.0.1:5173/?run=NEP-2027-VOLUME-2B_OCR&page=13&panel=tokens
```

The Vite development and preview servers expose repository data with PDF byte
range support. `npm run build` writes the static application to `dist/`; when
served from the repository tree it resolves data relative to the project root.
The current page's stage artifacts refresh every three seconds when **Live**
is explicitly enabled; polling is off by default. Live refresh does not reload
the PDF document or block interaction.

```bash
npm test
npm run build
```

PDF.js is pinned to `5.4.149`: the compatible, audit-clean release for the
workspace's Node 20 and Chromium versions. Do not replace the exact pin with a
caret range; PDF.js 6 requires newer JavaScript collection APIs.
