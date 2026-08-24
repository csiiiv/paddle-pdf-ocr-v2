# Static budget viewer

Public read-only viewer over frozen export packs. It never reads
`output/`, never calls a dev API, and shows no flags or QA data. The data
contract lives in
[`../docs/STATIC_VIEWER_CONTRACT.md`](../docs/STATIC_VIEWER_CONTRACT.md).

## Local development

```bash
# 1. Export a pack (optional if public/static-export/ is already populated)
python scripts/export_static_viewer.py --run NEP-2027-VOLUME-2B_OCR \
  --doc NEP-2027-VOLUME-2B --title "NEP FY 2027 Volume 2B" \
  --file-prefix "NEP-VOL2B DPWH" \
  --out viewer-react-static/public/static-export

# 2. Develop against the pack (Vite serves public/ and the root /static-export middleware)
cd viewer-react-static
npm install
npm run dev
# http://127.0.0.1:5174/?doc=NEP-2027-VOLUME-2B&tree=by-ou&page=13

npm test
npm run build
```

The production pack committed under `public/static-export/` is copied into
`dist/` on build. GitHub Pages deploys only that `dist/` via
`.github/workflows/deploy-static-viewer.yml` — the rest of the monorepo is
never published as a site.

PDF.js is pinned to `5.4.149` for parity with the debug viewer; do not
replace the exact pin with a caret range.
