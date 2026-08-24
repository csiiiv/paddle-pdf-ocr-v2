import {useEffect, useRef} from "react";

/** Modal listing every downloadable pack file for the current document. */
export default function DownloadModal({open, files, onClose}) {
  const dialog = useRef(null);

  useEffect(() => {
    if (!open) return;
    const onKey = (event) => { if (event.key === "Escape") onClose(); };
    addEventListener("keydown", onKey);
    dialog.current?.querySelector("button, a")?.focus();
    return () => removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  return <div className="modal-backdrop" role="presentation" onClick={onClose}>
    <div className="modal" role="dialog" aria-modal="true" aria-labelledby="download-modal-title"
         ref={dialog} onClick={(event) => event.stopPropagation()}>
      <div className="modal-header">
        <h2 id="download-modal-title">Download data</h2>
        <button type="button" className="modal-close" onClick={onClose} aria-label="Close">×</button>
      </div>
      <p className="muted modal-lead">Machine-readable extracts from the current document.</p>
      {!files.length
        ? <p className="muted">No downloadable files for this document.</p>
        : <ul className="download-list">
          {files.map((file) =>
            <li key={file.href}>
              <div className="download-meta">
                <strong>{file.name}</strong>
                <span className="muted">{file.treeLabel} · {file.format}</span>
              </div>
              <a className="download-btn" href={file.href} download={file.name}
                 target="_blank" rel="noreferrer">Download</a>
            </li>)}
        </ul>}
    </div>
  </div>;
}
