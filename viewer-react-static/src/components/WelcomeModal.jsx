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

/** First-visit overview; detailed controls live in per-pane info buttons. */
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
        <p>
          Browse machine-readable NEP budget tables beside the official PDF.
          The <strong>PDF pane</strong> shows the source document; the <strong>Data pane</strong>
          shows extracted hierarchy and amounts. Selections can sync between them.
        </p>

        <h3>Need help with controls?</h3>
        <p>
          Tap the <span className="inline-info-icon"><Icon name="info" size={16}/></span>{" "}
          <strong>info</strong> button in each pane for a quick guide to that pane&apos;s actions and features.
        </p>

        <h3>Also useful</h3>
        <ul>
          <li><strong>Download data</strong> — JSON and CSV extracts for analysis.</li>
          <li><strong>About</strong> — source PDF, repository, and disclaimer.</li>
          <li>Shareable links keep document, page, tree, and selection in the URL.</li>
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
