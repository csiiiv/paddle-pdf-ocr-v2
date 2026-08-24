import {useEffect, useRef, useState} from "react";
import Icon from "./Icon.jsx";

export const WELCOME_STORAGE_KEY = "budget-explorer-hide-welcome";

export const shouldShowWelcome = () => {
  try {
    return localStorage.getItem(WELCOME_STORAGE_KEY) !== "1";
  } catch {
    return true;
  }
};

export const persistHideWelcome = () => {
  try {
    localStorage.setItem(WELCOME_STORAGE_KEY, "1");
  } catch {
    /* private mode / blocked storage — ignore */
  }
};

/** First-visit overview of viewer controls and features. */
export default function WelcomeModal({open, onClose}) {
  const dialog = useRef(null);
  const [hideNext, setHideNext] = useState(false);
  const hideNextRef = useRef(false);
  hideNextRef.current = hideNext;

  const finish = () => {
    if (hideNextRef.current) persistHideWelcome();
    onClose();
  };

  useEffect(() => {
    if (!open) return;
    setHideNext(false);
    const onKey = (event) => { if (event.key === "Escape") finish(); };
    addEventListener("keydown", onKey);
    dialog.current?.querySelector("button")?.focus();
    return () => removeEventListener("keydown", onKey);
  }, [open]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!open) return null;

  return <div className="modal-backdrop" role="presentation" onClick={finish}>
    <div className="modal welcome-modal" role="dialog" aria-modal="true" aria-labelledby="welcome-modal-title"
         ref={dialog} onClick={(event) => event.stopPropagation()}>
      <div className="modal-header">
        <h2 id="welcome-modal-title">Welcome to NEP Budget Explorer</h2>
        <button type="button" className="modal-close" onClick={finish} aria-label="Close">
          <Icon name="close"/>
        </button>
      </div>
      <div className="about-body welcome-body">
        <p>Browse extracted NEP budget tables beside the official PDF.</p>

        <h3>PDF pane</h3>
        <ul>
          <li><strong>Click a row band on the PDF</strong> to select the matching tree entry.</li>
          <li><strong>Page</strong> — jump by number, or use the page arrows (and keyboard arrow keys).</li>
          <li><strong>Zoom</strong> — Fit W, Fit H, or a custom percent. On phones, pinch to zoom; one finger scrolls when zoomed in.</li>
          <li><strong>Row boxes</strong> — Show overlays, Hide them but keep clicks, or turn Off.</li>
        </ul>

        <h3>Tree pane</h3>
        <ul>
          <li><strong>Click a row in tree data </strong> to select it and sync the PDF (toast if it has no bbox).</li>
          <li>Switch <strong>By Operating Unit</strong> and <strong>PAP</strong> with the tabs.</li>
          <li>Expand/collapse with the tree chevrons; search filters label, code, and kind.</li>
        </ul>

        <h3>Also useful</h3>
        <ul>
          <li><strong>Download data</strong> — JSON and CSV extracts for analysis.</li>
          <li><strong>About</strong> (footer) — source PDF, repository, and disclaimer.</li>
          <li>On desktop, drag the center splitter to resize the panes.</li>
          <li>On phones, use the compact <strong>PDF | Data</strong> switch. Selecting a PDF row jumps to Data and focuses the matching tree entry; selecting a tree row with a PDF location jumps to PDF. Page with the floating arrows / page chip; open extra PDF or tree options from the floating buttons.</li>
        </ul>
      </div>
      <div className="welcome-footer">
        <label className="check welcome-dismiss">
          <input type="checkbox" checked={hideNext} onChange={(e) => setHideNext(e.target.checked)}/>
          Don&apos;t show again
        </label>
        <button type="button" className="welcome-start" onClick={finish}>Get started</button>
      </div>
    </div>
  </div>;
}
