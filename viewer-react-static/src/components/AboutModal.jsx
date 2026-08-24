import {useEffect, useRef} from "react";
import Icon from "./Icon.jsx";

const REPO_URL = "https://github.com/csiiiv/paddle-pdf-ocr-v2";
const SOURCE_PDF_URL = "https://www.dbm.gov.ph/wp-content/uploads/NEP2027/NEP-2027-VOLUME-2B.pdf";
const DBM_URL = "https://www.dbm.gov.ph/";
const PAGES_URL = "https://csiiiv.github.io/paddle-pdf-ocr-v2/";

/** About / credits dialog for the public static viewer. */
export default function AboutModal({open, onClose}) {
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
    <div className="modal about-modal" role="dialog" aria-modal="true" aria-labelledby="about-modal-title"
         ref={dialog} onClick={(event) => event.stopPropagation()}>
      <div className="modal-header">
        <h2 id="about-modal-title">About</h2>
        <button type="button" className="modal-close" onClick={onClose} aria-label="Close">
          <Icon name="close"/>
        </button>
      </div>
      <div className="about-body">
        <p>
          <strong>NEP Budget Explorer</strong> is a read-only viewer for machine-readable
          extracts of the Philippine National Expenditure Program (NEP). It syncs
          hierarchical budget tables with the source PDF so you can browse By
          Operating Unit and PAP rows alongside the original pages.
        </p>

        <h3>Source</h3>
        <ul>
          <li>
            Official PDF:{" "}
            <a href={SOURCE_PDF_URL} target="_blank" rel="noreferrer">
              NEP 2027 · Volume 2B
            </a>{" "}
            (Department of Budget and Management)
          </li>
          <li>
            Publisher:{" "}
            <a href={DBM_URL} target="_blank" rel="noreferrer">dbm.gov.ph</a>
          </li>
        </ul>

        <h3>Project</h3>
        <ul>
          <li>
            Source code:{" "}
            <a href={REPO_URL} target="_blank" rel="noreferrer">csiiiv/paddle-pdf-ocr-v2</a>
          </li>
          <li>
            This site:{" "}
            <a href={PAGES_URL} target="_blank" rel="noreferrer">{PAGES_URL.replace(/^https:\/\//, "")}</a>
          </li>
          <li>
            Contract &amp; schema:{" "}
            <a href={`${REPO_URL}/blob/main/docs/STATIC_VIEWER_CONTRACT.md`} target="_blank" rel="noreferrer">
              STATIC_VIEWER_CONTRACT.md
            </a>
          </li>
        </ul>

        <h3>Acknowledgments</h3>
        <ul>
          <li>Department of Budget and Management for publishing the NEP volumes.</li>
          <li>Mozilla PDF.js for in-browser PDF rendering.</li>
          <li>React, Vite, and the broader open-source tooling used to build this viewer.</li>
        </ul>

        <h3>Disclaimer</h3>
        <p className="muted">
          This is an unofficial civic-tech extract. Figures and hierarchy may
          contain OCR or structure errors. Always verify critical amounts against
          the official DBM PDF. Not affiliated with the Philippine government.
        </p>
      </div>
    </div>
  </div>;
}
