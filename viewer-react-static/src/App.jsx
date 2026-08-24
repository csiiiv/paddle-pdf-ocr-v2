import {useEffect, useMemo, useRef, useState} from "react";
import {loadIndex, loadManifest, loadTree, pdfHref, treeDownloads} from "./lib/api.js";
import {parseView, writeView} from "./lib/viewState.js";
import DownloadModal from "./components/DownloadModal.jsx";
import PdfPane from "./components/PdfPane.jsx";
import TreePanel from "./components/TreePanel.jsx";

export default function App() {
  const initial = useMemo(() => parseView(new URLSearchParams(location.search)), []);
  const [docs, setDocs] = useState([]);
  const [doc, setDoc] = useState(initial.doc);
  const [manifest, setManifest] = useState(null);
  const [treeId, setTreeId] = useState(initial.tree);
  const [tree, setTree] = useState(null);
  const [treeLoading, setTreeLoading] = useState(false);
  const [page, setPage] = useState(initial.page);
  const [selectedNode, setSelectedNode] = useState(null);
  const [zoom, setZoom] = useState(initial.zoom);
  const [split, setSplit] = useState(initial.split);
  const [overlayMode, setOverlayMode] = useState(initial.overlay);
  const [downloadOpen, setDownloadOpen] = useState(false);
  const [pdfPageCount, setPdfPageCount] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const dragging = useRef(false);

  // Load the multi-doc index once; fall back to the first document.
  useEffect(() => {
    loadIndex()
      .then((index) => {
        const names = (index?.docs || []).map((entry) => entry.doc);
        setDocs(names);
        setDoc((current) => current || names[0] || "");
      })
      .catch((reason) => setError(`index: ${reason.message}`))
      .finally(() => setLoading(false));
  }, []);

  // Load the manifest whenever the document changes.
  useEffect(() => {
    if (!doc) return;
    let live = true;
    setManifest(null); setTree(null); setSelectedNode(null); setError("");
    setPdfPageCount(null);
    loadManifest(doc)
      .then((next) => {
        if (!live) return;
        if (next.format !== 1) throw new Error(`Unsupported manifest format ${next.format}`);
        setManifest(next);
        setTreeId((current) => next.trees.some((item) => item.id === current) ? current : next.trees[0]?.id || "");
        // Prefer the full PDF page count from the manifest until PDF.js reports it.
        if (next.pdf?.pages) setPdfPageCount(next.pdf.pages);
        setPage((current) => current ?? 1);
      })
      .catch((reason) => { if (live) setError(reason.message); });
    return () => { live = false; };
  }, [doc]);

  // Lazy-load the active tree only when its tab is selected.
  useEffect(() => {
    if (!doc || !manifest || !treeId) return;
    const meta = manifest.trees.find((item) => item.id === treeId);
    if (!meta) return;
    let live = true;
    setTree(null); setTreeLoading(true);
    loadTree(doc, meta.file)
      .then((next) => {
        if (!live) return;
        if (next.format !== 1) throw new Error(`Unsupported tree format ${next.format}`);
        setTree(next);
      })
      .catch((reason) => { if (live) setError(reason.message); })
      .finally(() => { if (live) setTreeLoading(false); });
    return () => { live = false; };
  }, [doc, manifest, treeId]);

  // Keep page inside the full PDF range (not just tree-covered pages).
  useEffect(() => {
    if (!pdfPageCount) return;
    if (!page || page < 1 || page > pdfPageCount) setPage(1);
  }, [pdfPageCount, page]);

  // Retain shareable state in the URL.
  useEffect(() => {
    const params = new URLSearchParams();
    writeView(params, {doc, tree:treeId, page, node:selectedNode?.id || "", zoom, split, overlay:overlayMode});
    history.replaceState(null, "", `${location.pathname}?${params.toString()}`);
  }, [doc, treeId, page, selectedNode, zoom, split, overlayMode]);

  useEffect(() => {
    const move = (e) => { if (dragging.current) setSplit(Math.max(32, Math.min(76, e.clientX / innerWidth * 100))); };
    const up = () => { dragging.current = false; document.body.classList.remove("dragging"); };
    addEventListener("pointermove", move); addEventListener("pointerup", up);
    return () => { removeEventListener("pointermove", move); removeEventListener("pointerup", up); };
  }, []);

  // Full PDF page list — tree-only pages would hide covers, dividers, notes.
  const pages = useMemo(
    () => pdfPageCount ? Array.from({length: pdfPageCount}, (_, i) => i + 1) : [],
    [pdfPageCount],
  );
  const at = pages.indexOf(page);
  const keyboardNav = (event) => {
    if (event.target.matches("input,select")) return;
    if (event.key === "ArrowLeft" && at > 0) setPage(pages[at - 1]);
    if (event.key === "ArrowRight" && at >= 0 && at < pages.length - 1) setPage(pages[at + 1]);
  };
  useEffect(() => {
    addEventListener("keydown", keyboardNav);
    return () => removeEventListener("keydown", keyboardNav);
  }, [at, pages.length]);

  const selectNode = (node) => {
    setSelectedNode(node);
    if (node?.page) setPage(node.page);
  };

  // Nodes of the current page, for clickable PDF overlays.
  const pageNodes = useMemo(() => {
    if (!tree || !page) return [];
    return tree.nodes.filter((node) => node.page === page && node.bbox);
  }, [tree, page]);

  // Restore a shared-link node selection once its tree is loaded.
  useEffect(() => {
    if (!tree || !initial.node || selectedNode) return;
    const node = tree.nodes?.find((item) => item.id === initial.node);
    if (node) {
      setSelectedNode(node);
      if (node.page) setPage(node.page);
    }
  }, [tree, initial.node]); // eslint-disable-line react-hooks/exhaustive-deps

  const status = error || (loading ? "Loading…" : treeLoading ? "Loading tree…"
    : `${doc}${treeId ? ` · ${treeId}` : ""} · ${tree?.nodes?.length ?? 0} nodes · p.${page ?? "—"}`);

  // Flat list of downloadable pack files (JSON + CSV per tree).
  const downloadFiles = useMemo(
    () => (manifest?.trees || []).flatMap((meta) => treeDownloads(doc, meta)),
    [manifest, doc],
  );

  return <div className="app">
    <header>
      <div className="brand"><strong>Budget Explorer</strong><span>static export</span></div>
      <div className="group"><label>Document</label>
        <select value={doc} onChange={(e) => { setDoc(e.target.value); setTreeId(""); setPage(null); }} aria-label="Document">
          {docs.map((name) => <option key={name} value={name}>{name}</option>)}
        </select>
      </div>
      {downloadFiles.length > 0 &&
        <button type="button" onClick={() => setDownloadOpen(true)}>Download data</button>}
      <div className="group zoom">
        <button className={zoom.mode === "fit" ? "active" : ""} onClick={() => setZoom({mode:"fit", percent:100})}>Fit W</button>
        <button className={zoom.mode === "height" ? "active" : ""} onClick={() => setZoom({mode:"height", percent:100})}>Fit H</button>
        <button onClick={() => setZoom({mode:"custom", percent:Math.max(25, zoom.percent - 10)})}>−</button>
        <input type="number" min="25" max="400" value={zoom.percent} onChange={(e) => setZoom({mode:"custom", percent:Number(e.target.value)})}/>
        <span>%</span>
        <button onClick={() => setZoom({mode:"custom", percent:Math.min(400, zoom.percent + 10)})}>+</button>
      </div>
      <span className={`status ${error ? "error" : ""}`}>{status}</span>
    </header>
    <DownloadModal open={downloadOpen} files={downloadFiles} onClose={() => setDownloadOpen(false)} />
    <main style={{gridTemplateColumns:`minmax(360px,${split}%) 6px minmax(300px,1fr)`}}>
      <div className="pdf-pane">
        <div className="pdf-toolbar">
          <div className="group"><label>Page</label>
            <button disabled={at <= 0} onClick={() => setPage(pages[at - 1])} aria-label="Previous page">←</button>
            <select value={pages.includes(page) ? page : (pages[0] ?? "")} onChange={(e) => setPage(Number(e.target.value))} disabled={!pages.length} aria-label="Page">
              {pages.map((p) => <option key={p} value={p}>{p}</option>)}
            </select>
            <button disabled={at < 0 || at === pages.length - 1} onClick={() => setPage(pages[at + 1])} aria-label="Next page">→</button>
            <span className="muted">{pages.length ? `${at + 1} / ${pages.length}` : "—"}</span>
          </div>
          <div className="group"><label>Row boxes</label>
            <select value={overlayMode} onChange={(e) => setOverlayMode(e.target.value)} aria-label="Row bounding boxes">
              <option value="show">Show</option>
              <option value="hide">Hide (clickable)</option>
              <option value="off">Off</option>
            </select>
          </div>
        </div>
        <PdfPane pdfUrl={manifest ? pdfHref(manifest) : null} page={page} highlight={selectedNode}
                 pageNodes={pageNodes} overlayMode={overlayMode} onNodeClick={selectNode}
                 onDocumentLoad={setPdfPageCount} />
      </div>
      <div className="splitter" onPointerDown={() => { dragging.current = true; document.body.classList.add("dragging"); }}/>
      <aside>
        <div className="panel-tabs" role="tablist" aria-label="Tree selection">
          {(manifest?.trees || []).map((meta) =>
            <button key={meta.id} role="tab" aria-selected={meta.id === treeId} className={meta.id === treeId ? "active" : ""} onClick={() => setTreeId(meta.id)}>{meta.label}</button>)}
        </div>
        <div className="panel">
          {treeLoading && <p className="muted">Loading tree…</p>}
          {!treeLoading && !error && <TreePanel tree={tree} currentPage={page} selectedId={selectedNode?.id} onSelect={selectNode} />}
        </div>
      </aside>
    </main>
    <footer>{selectedNode ? `${selectedNode.label || selectedNode.id}` : "No selection"}</footer>
  </div>;
}
