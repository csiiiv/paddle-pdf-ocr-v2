import {useEffect, useMemo, useRef, useState} from "react";
import {loadIndex, loadManifest, loadTree, pdfHref, treeDownloads} from "./lib/api.js";
import {DEFAULT_PANE, PANE_MODES, parseView, writeView, DEFAULT_HIERARCHY, HIERARCHY_MODES} from "./lib/viewState.js";
import DownloadModal from "./components/DownloadModal.jsx";
import AboutModal from "./components/AboutModal.jsx";
import WelcomeModal, {shouldShowWelcome} from "./components/WelcomeModal.jsx";
import PaneHelpModal from "./components/PaneHelpModal.jsx";
import {DataPaneHelpContent, PdfPaneHelpContent} from "./lib/paneHelpContent.jsx";
import PdfPane from "./components/PdfPane.jsx";
import PdfToolbar from "./components/PdfToolbar.jsx";
import Icon from "./components/Icon.jsx";
import TreePanel from "./components/TreePanel.jsx";
import {useViewportLayout} from "./lib/useViewportLayout.js";
import {isNodeInSearchResults} from "./lib/treeSearch.js";

export default function App() {
  const initial = useMemo(() => parseView(new URLSearchParams(location.search)), []);
  const {isMobile, landscape} = useViewportLayout();
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
  const [syncEnabled, setSyncEnabled] = useState(true);
  const [mobilePane, setMobilePane] = useState(() => {
    const raw = new URLSearchParams(location.search).get("pane");
    if (PANE_MODES.includes(raw)) return raw;
    if (initial.node || initial.page) return "pdf";
    return DEFAULT_PANE;
  });
  const [hierarchyMode, setHierarchyMode] = useState(initial.hierarchy);
  const [downloadOpen, setDownloadOpen] = useState(false);
  const [aboutOpen, setAboutOpen] = useState(false);
  const [welcomeOpen, setWelcomeOpen] = useState(() => shouldShowWelcome());
  const [pdfHelpOpen, setPdfHelpOpen] = useState(false);
  const [dataHelpOpen, setDataHelpOpen] = useState(false);
  const [pdfSheetOpen, setPdfSheetOpen] = useState(false);
  const [dataSheetOpen, setDataSheetOpen] = useState(false);
  const [pdfPageCount, setPdfPageCount] = useState(null);
  const [toast, setToast] = useState("");
  const [toastTick, setToastTick] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const dragging = useRef(false);
  const toastTimer = useRef(null);
  const searchFilter = useRef({active: false, included: null});

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
        if (next.format !== 1 && next.format !== 2) throw new Error(`Unsupported tree format ${next.format}`);
        setTree(next);
      })
      .catch((reason) => { if (live) setError(reason.message); })
      .finally(() => { if (live) setTreeLoading(false); });
    return () => { live = false; };
  }, [doc, manifest, treeId]);

  useEffect(() => {
    if (treeId !== "by-ou" && hierarchyMode !== DEFAULT_HIERARCHY) {
      setHierarchyMode(DEFAULT_HIERARCHY);
    }
  }, [treeId, hierarchyMode]);

  // Keep page inside the full PDF range (clamp under/overflow; never hard-reset to 1 on overflow).
  useEffect(() => {
    if (!pdfPageCount) return;
    setPage((current) => {
      const n = Math.trunc(Number(current));
      if (!Number.isFinite(n) || n < 1) return 1;
      if (n > pdfPageCount) return pdfPageCount;
      return n;
    });
  }, [pdfPageCount]);

  // Retain shareable state in the URL.
  useEffect(() => {
    const params = new URLSearchParams();
    writeView(params, {
      doc, tree:treeId, page, node:selectedNode?.id || "", zoom, split,
      overlay:overlayMode, pane:isMobile ? mobilePane : DEFAULT_PANE, hierarchy:hierarchyMode,
    });
    history.replaceState(null, "", `${location.pathname}?${params.toString()}`);
  }, [doc, treeId, page, selectedNode, zoom, split, overlayMode, isMobile, mobilePane, hierarchyMode]);

  useEffect(() => {
    const move = (e) => {
      if (!dragging.current || isMobile) return;
      setSplit(Math.max(32, Math.min(76, e.clientX / innerWidth * 100)));
    };
    const up = () => { dragging.current = false; document.body.classList.remove("dragging"); };
    addEventListener("pointermove", move); addEventListener("pointerup", up);
    return () => { removeEventListener("pointermove", move); removeEventListener("pointerup", up); };
  }, [isMobile]);

  useEffect(() => {
    if (!isMobile) {
      setPdfSheetOpen(false);
      setDataSheetOpen(false);
    }
  }, [isMobile]);

  const clampPage = (value) => {
    if (!pdfPageCount) return null;
    const n = Math.trunc(Number(value));
    if (!Number.isFinite(n)) return 1;
    return Math.min(pdfPageCount, Math.max(1, n));
  };
  const goToPage = (value) => {
    const next = clampPage(value);
    if (next != null) setPage(next);
  };

  // Draft lets the field go empty while typing; committed page stays clamped.
  const [pageDraft, setPageDraft] = useState(() => (initial.page == null ? "" : String(initial.page)));
  useEffect(() => { setPageDraft(page == null ? "" : String(page)); }, [page]);
  const commitPageDraft = () => goToPage(pageDraft === "" ? 1 : pageDraft);

  const keyboardNav = (event) => {
    if (event.target.matches("input,select,textarea")) return;
    if (!page || !pdfPageCount) return;
    if (event.key === "ArrowLeft" && page > 1) goToPage(page - 1);
    if (event.key === "ArrowRight" && page < pdfPageCount) goToPage(page + 1);
  };
  useEffect(() => {
    addEventListener("keydown", keyboardNav);
    return () => removeEventListener("keydown", keyboardNav);
  }, [page, pdfPageCount]);

  const showToast = (message) => {
    if (toastTimer.current) clearTimeout(toastTimer.current);
    setToast(message);
    // Remount so the nudge animation replays even for the same message.
    setToastTick((tick) => tick + 1);
    toastTimer.current = setTimeout(() => setToast(""), 2800);
  };
  useEffect(() => () => { if (toastTimer.current) clearTimeout(toastTimer.current); }, []);

  const hasBbox = (node) => Array.isArray(node?.bbox) && node.bbox.length === 4;

  const selectNode = (node, {fromTree = false} = {}) => {
    // Sync off: tree still selects locally; PDF clicks are ignored (no onNodeClick).
    if (!syncEnabled) {
      if (fromTree) setSelectedNode(node);
      return;
    }
    setSelectedNode(node);
    if (node?.page) setPage(node.page);
    if (!fromTree && searchFilter.current.active
        && !isNodeInSearchResults(node?.id, searchFilter.current.included)) {
      showToast("selection not in search results");
    }
    if (node && !hasBbox(node)) {
      showToast("no bbox in pdf");
      return;
    }
    if (!isMobile || !node) return;
    // Tree → PDF when the row maps onto the page; PDF → Data so the row is focused.
    if (fromTree && hasBbox(node)) setMobilePane("pdf");
    else if (!fromTree) setMobilePane("data");
  };

  // Every node on this page that has a row bbox — leaves and parents alike.
  const pageNodes = useMemo(() => {
    if (!tree || !page) return [];
    return tree.nodes.filter((node) => Number(node.page) === Number(page) && Array.isArray(node.bbox) && node.bbox.length === 4);
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

  const pdfToolbarProps = {
    page, pageDraft, pdfPageCount, zoom,
    overlayMode, syncEnabled,
    onPrev: () => goToPage(page - 1),
    onNext: () => goToPage(page + 1),
    onPageChange: (value) => { setPageDraft(value); if (value !== "") goToPage(value); },
    onPageBlur: commitPageDraft,
    onZoom: setZoom,
    onOverlay: setOverlayMode,
    onSync: () => setSyncEnabled((on) => !on),
    onHelp: () => setPdfHelpOpen(true),
  };

  const mainStyle = isMobile ? undefined : {
    gridTemplateColumns: `minmax(360px,${split}%) 6px minmax(300px,1fr)`,
  };

  return <div className={`app${isMobile ? " is-mobile" : ""}${isMobile && landscape ? " is-landscape" : ""}`}>
    <header>
      {isMobile
        ? <div className="mobile-top">
            <div className="mobile-top-row">
              <strong className="mobile-brand">NEP Explorer</strong>
              <select className="mobile-doc" value={doc}
                      onChange={(e) => { setDoc(e.target.value); setTreeId(""); setPage(null); }}
                      aria-label="Document">
                {docs.map((name) => <option key={name} value={name}>{name}</option>)}
              </select>
              {downloadFiles.length > 0 &&
                <button type="button" className="mobile-icon-btn" onClick={() => setDownloadOpen(true)} aria-label="Download data">
                  <Icon name="download"/>
                </button>}
              <button type="button" className="mobile-icon-btn" onClick={() => setAboutOpen(true)} aria-label="About">
                <Icon name="info"/>
              </button>
            </div>
            <div className="mobile-switch" role="tablist" aria-label="View mode">
              <button type="button" role="tab" aria-selected={mobilePane === "pdf"}
                      className={mobilePane === "pdf" ? "active" : ""}
                      onClick={() => { setMobilePane("pdf"); setDataSheetOpen(false); }}>PDF</button>
              <button type="button" role="tab" aria-selected={mobilePane === "data"}
                      className={mobilePane === "data" ? "active" : ""}
                      onClick={() => { setMobilePane("data"); setPdfSheetOpen(false); }}>Data</button>
            </div>
          </div>
        : <>
            <div className="brand"><strong>NEP Budget Explorer</strong><span>static export</span></div>
            <div className="group"><label>Document</label>
              <select value={doc} onChange={(e) => { setDoc(e.target.value); setTreeId(""); setPage(null); }} aria-label="Document">
                {docs.map((name) => <option key={name} value={name}>{name}</option>)}
              </select>
            </div>
            {downloadFiles.length > 0 &&
              <button type="button" onClick={() => setDownloadOpen(true)}>Download data</button>}
            <span className={`status ${error ? "error" : ""}`}>{status}</span>
          </>}
    </header>
    <DownloadModal open={downloadOpen} files={downloadFiles} onClose={() => setDownloadOpen(false)} />
    <AboutModal open={aboutOpen} onClose={() => setAboutOpen(false)} />
    <WelcomeModal open={welcomeOpen} onClose={() => setWelcomeOpen(false)} />
    <PaneHelpModal open={pdfHelpOpen} title="PDF pane" onClose={() => setPdfHelpOpen(false)}>
      <PdfPaneHelpContent isMobile={isMobile}/>
    </PaneHelpModal>
    <PaneHelpModal open={dataHelpOpen} title="Data pane" onClose={() => setDataHelpOpen(false)}>
      <DataPaneHelpContent isMobile={isMobile}/>
    </PaneHelpModal>
    {toast && <div key={toastTick} className="toast" role="status" aria-live="polite">{toast}</div>}
    <main className={isMobile ? "mobile-layout" : undefined}
          data-pane={isMobile ? mobilePane : undefined}
          style={mainStyle}>
      <div className="pdf-pane">
        {!isMobile && <div className="pdf-toolbar"><PdfToolbar {...pdfToolbarProps}/></div>}
        <div className="pdf-view">
          <PdfPane pdfUrl={manifest ? pdfHref(manifest) : null} page={page}
                   highlight={syncEnabled ? selectedNode : null}
                   pageNodes={pageNodes} overlayMode={overlayMode} zoom={zoom}
                   onNodeClick={syncEnabled ? ((node) => selectNode(node)) : undefined}
                   onDocumentLoad={setPdfPageCount}
                   onZoomChange={setZoom} pinchZoom={isMobile} />
          {isMobile &&
            <button type="button" className="fab fab-help-pdf" onClick={() => setPdfHelpOpen(true)}
                    aria-label="PDF pane help">
              <Icon name="info" size={24}/>
            </button>}
          {isMobile &&
            <div className="fab-stack">
              <button type="button" className="fab" disabled={!page || page <= 1}
                      onClick={() => goToPage(page - 1)} aria-label="Previous page">
                <Icon name="chevron_left" size={24}/>
              </button>
              <button type="button" className="fab fab-page"
                      onClick={() => setPdfSheetOpen(true)}
                      aria-label="PDF tools">
                {page ?? "—"}
                <span>{pdfPageCount ? `/ ${pdfPageCount}` : ""}</span>
              </button>
              <button type="button" className="fab" disabled={!page || !pdfPageCount || page >= pdfPageCount}
                      onClick={() => goToPage(page + 1)} aria-label="Next page">
                <Icon name="chevron_right" size={24}/>
              </button>
            </div>}
        </div>
      </div>
      <div className="splitter" onPointerDown={() => {
        if (isMobile) return;
        dragging.current = true;
        document.body.classList.add("dragging");
      }}/>
      <aside>
        {!isMobile &&
          <div className="panel-tabs" role="tablist" aria-label="Tree selection">
            {(manifest?.trees || []).map((meta) =>
              <button key={meta.id} role="tab" aria-selected={meta.id === treeId} className={meta.id === treeId ? "active" : ""} onClick={() => setTreeId(meta.id)}>{meta.label}</button>)}
            <button type="button" className="pane-info-btn" onClick={() => setDataHelpOpen(true)}
                    aria-label="Data pane help">
              <Icon name="info"/>
            </button>
          </div>}
        <div className="panel">
          {treeLoading && <p className="muted">Loading tree…</p>}
          {!treeLoading && !error &&
            <TreePanel tree={tree} currentPage={page} selectedId={selectedNode?.id} compact={isMobile}
                       active={!isMobile || mobilePane === "data"}
                       hierarchyMode={treeId === "by-ou" ? hierarchyMode : DEFAULT_HIERARCHY}
                       onHierarchyModeChange={(mode) => {
                         if (HIERARCHY_MODES.includes(mode)) setHierarchyMode(mode);
                       }}
                       onOpenHelp={isMobile ? () => setDataHelpOpen(true) : undefined}
                       onSearchFilterChange={(next) => { searchFilter.current = next; }}
                       onSelect={(node) => selectNode(node, {fromTree:true})} />}
        </div>
        {isMobile &&
          <button type="button" className="fab fab-data" onClick={() => setDataSheetOpen(true)}
                  aria-label="Tree options">
            <Icon name="menu" size={24}/>
          </button>}
      </aside>
    </main>
    {isMobile && pdfSheetOpen &&
      <div className="sheet-backdrop" onClick={() => setPdfSheetOpen(false)}>
        <div className="sheet" role="dialog" aria-label="PDF tools" onClick={(e) => e.stopPropagation()}>
          <div className="sheet-handle"/>
          <div className="pdf-toolbar sheet-toolbar">
            <PdfToolbar {...pdfToolbarProps} layout="sheet" onHelp={undefined}/>
          </div>
          <button type="button" className="sheet-done" onClick={() => setPdfSheetOpen(false)}>Done</button>
        </div>
      </div>}
    {isMobile && dataSheetOpen &&
      <div className="sheet-backdrop" onClick={() => setDataSheetOpen(false)}>
        <div className="sheet" role="dialog" aria-label="Tree options" onClick={(e) => e.stopPropagation()}>
          <div className="sheet-handle"/>
          <p className="sheet-title">Tree</p>
          <div className="panel-tabs sheet-tabs" role="tablist" aria-label="Tree selection">
            {(manifest?.trees || []).map((meta) =>
              <button key={meta.id} role="tab" aria-selected={meta.id === treeId}
                      className={meta.id === treeId ? "active" : ""}
                      onClick={() => { setTreeId(meta.id); setDataSheetOpen(false); }}>{meta.label}</button>)}
          </div>
          <button type="button" className="sheet-done" onClick={() => setDataSheetOpen(false)}>Done</button>
        </div>
      </div>}
    <footer>
      <span className="footer-status">{selectedNode ? `${selectedNode.label || selectedNode.id}` : "No selection"}</span>
      {!isMobile && <button type="button" className="footer-about" onClick={() => setAboutOpen(true)}>About</button>}
    </footer>
  </div>;
}
