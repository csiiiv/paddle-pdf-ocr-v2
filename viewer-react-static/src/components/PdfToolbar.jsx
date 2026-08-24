/** Shared PDF page / zoom / overlay / sync controls. */
import Icon from "./Icon.jsx";

export default function PdfToolbar({
  page, pageDraft, pdfPageCount, zoom, overlayMode, syncEnabled,
  onPrev, onNext, onPageChange, onPageBlur, onZoom, onOverlay, onSync, onHelp,
  layout = "desktop",
}) {
  const isSheet = layout === "sheet";

  const viewSection = (
    <section className="pdf-toolbar-section pdf-toolbar-view" aria-label="PDF view options">
      <span className="pdf-toolbar-label">Row boxes</span>
      <div className="pdf-toolbar-controls">
        <select value={overlayMode} onChange={(e) => onOverlay(e.target.value)} aria-label="Row bounding boxes">
          <option value="show">Show</option>
          <option value="hide">Hide (clickable)</option>
          <option value="off">Off</option>
        </select>
        <button type="button" className={syncEnabled ? "active" : ""}
                aria-pressed={syncEnabled}
                title={syncEnabled ? "Disable PDF sync" : "Enable PDF sync"}
                onClick={onSync}>
          {syncEnabled ? "Sync on" : "Sync off"}
        </button>
      </div>
    </section>
  );

  const pageSection = (
    <section className="pdf-toolbar-section pdf-toolbar-nav" aria-label="Page navigation">
      <span className="pdf-toolbar-label">Page</span>
      <div className="pdf-toolbar-controls">
        <button type="button" disabled={!page || page <= 1} onClick={onPrev} aria-label="Previous page">
          <Icon name="chevron_left"/>
        </button>
        <input type="number" className="page-input" inputMode="numeric" min={1}
               max={pdfPageCount || undefined} value={pageDraft} disabled={!pdfPageCount}
               aria-label="Page number" onChange={(e) => onPageChange(e.target.value)}
               onBlur={onPageBlur}
               onKeyDown={(e) => { if (e.key === "Enter") e.currentTarget.blur(); }}/>
        <span className="pdf-page-total">{pdfPageCount ? `/ ${pdfPageCount}` : "—"}</span>
        <button type="button" disabled={!page || !pdfPageCount || page >= pdfPageCount} onClick={onNext} aria-label="Next page">
          <Icon name="chevron_right"/>
        </button>
      </div>
    </section>
  );

  const zoomSection = (
    <section className="pdf-toolbar-section pdf-toolbar-zoom" aria-label="Zoom">
      <span className="pdf-toolbar-label">Zoom</span>
      <div className="pdf-toolbar-controls">
        <button type="button" className={zoom.mode === "fit" ? "active" : ""} onClick={() => onZoom({mode:"fit", percent:100})}>Fit W</button>
        <button type="button" className={zoom.mode === "height" ? "active" : ""} onClick={() => onZoom({mode:"height", percent:100})}>Fit H</button>
        <button type="button" onClick={() => onZoom({mode:"custom", percent:Math.max(25, zoom.percent - 10)})} aria-label="Zoom out">
          <Icon name="remove"/>
        </button>
        <input type="number" min="25" max="400" value={zoom.percent}
               onChange={(e) => onZoom({mode:"custom", percent:Math.max(25, Math.min(400, Number(e.target.value) || 100))})}
               aria-label="Zoom percent"/>
        <span className="pdf-zoom-suffix">%</span>
        <button type="button" onClick={() => onZoom({mode:"custom", percent:Math.min(400, zoom.percent + 10)})} aria-label="Zoom in">
          <Icon name="add"/>
        </button>
      </div>
    </section>
  );

  if (isSheet) {
    return (
      <div className="pdf-toolbar-inner pdf-toolbar-inner-sheet">
        {viewSection}
        {pageSection}
        {zoomSection}
      </div>
    );
  }

  return (
    <div className="pdf-toolbar-inner">
      <div className="pdf-toolbar-slot pdf-toolbar-slot-left">{viewSection}</div>
      <div className="pdf-toolbar-slot pdf-toolbar-slot-center">{pageSection}</div>
      <div className="pdf-toolbar-slot pdf-toolbar-slot-right">
        {zoomSection}
        {onHelp &&
          <button type="button" className="pane-info-btn pdf-toolbar-help" onClick={onHelp} aria-label="PDF pane help">
            <Icon name="info"/>
          </button>}
      </div>
    </div>
  );
}
