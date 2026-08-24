/** Shared PDF page / zoom / overlay / sync controls. */
import Icon from "./Icon.jsx";

export default function PdfToolbar({
  page, pageDraft, pdfPageCount, zoom, overlayMode, syncEnabled,
  onPrev, onNext, onPageChange, onPageBlur, onZoom, onOverlay, onSync,
}) {
  return <>
    <div className="group"><label>Page</label>
      <button type="button" disabled={!page || page <= 1} onClick={onPrev} aria-label="Previous page">
        <Icon name="chevron_left"/>
      </button>
      <input type="number" className="page-input" inputMode="numeric" min={1}
             max={pdfPageCount || undefined} value={pageDraft} disabled={!pdfPageCount}
             aria-label="Page" onChange={(e) => onPageChange(e.target.value)}
             onBlur={onPageBlur}
             onKeyDown={(e) => { if (e.key === "Enter") e.currentTarget.blur(); }}/>
      <button type="button" disabled={!page || !pdfPageCount || page >= pdfPageCount} onClick={onNext} aria-label="Next page">
        <Icon name="chevron_right"/>
      </button>
      <span className="muted">{pdfPageCount ? `/ ${pdfPageCount}` : "—"}</span>
    </div>
    <div className="group zoom"><label>Zoom</label>
      <button type="button" className={zoom.mode === "fit" ? "active" : ""} onClick={() => onZoom({mode:"fit", percent:100})}>Fit W</button>
      <button type="button" className={zoom.mode === "height" ? "active" : ""} onClick={() => onZoom({mode:"height", percent:100})}>Fit H</button>
      <button type="button" onClick={() => onZoom({mode:"custom", percent:Math.max(25, zoom.percent - 10)})} aria-label="Zoom out">
        <Icon name="remove"/>
      </button>
      <input type="number" min="25" max="400" value={zoom.percent}
             onChange={(e) => onZoom({mode:"custom", percent:Math.max(25, Math.min(400, Number(e.target.value) || 100))})}
             aria-label="Zoom percent"/>
      <span>%</span>
      <button type="button" onClick={() => onZoom({mode:"custom", percent:Math.min(400, zoom.percent + 10)})} aria-label="Zoom in">
        <Icon name="add"/>
      </button>
    </div>
    <div className="group"><label>Row boxes</label>
      <select value={overlayMode} onChange={(e) => onOverlay(e.target.value)} aria-label="Row bounding boxes">
        <option value="show">Show</option>
        <option value="hide">Hide (clickable)</option>
        <option value="off">Off</option>
      </select>
    </div>
    <div className="group">
      <button type="button" className={syncEnabled ? "active" : ""}
              aria-pressed={syncEnabled}
              title={syncEnabled ? "Disable PDF sync" : "Enable PDF sync"}
              onClick={onSync}>
        {syncEnabled ? "Sync on" : "Sync off"}
      </button>
    </div>
  </>;
}
