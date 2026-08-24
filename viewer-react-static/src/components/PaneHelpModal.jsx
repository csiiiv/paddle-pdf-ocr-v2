import {useEffect, useRef} from "react";
import Icon from "./Icon.jsx";

/** Context help for one viewer pane (PDF or Data). */
export default function PaneHelpModal({open, title, onClose, children}) {
  const dialog = useRef(null);

  useEffect(() => {
    if (!open) return;
    const onKey = (event) => { if (event.key === "Escape") onClose(); };
    addEventListener("keydown", onKey);
    dialog.current?.querySelector("button")?.focus();
    return () => removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  return <div className="modal-backdrop" role="presentation" onClick={onClose}>
    <div className="modal pane-help-modal" role="dialog" aria-modal="true"
         aria-labelledby="pane-help-title" ref={dialog}
         onClick={(event) => event.stopPropagation()}>
      <div className="modal-header">
        <h2 id="pane-help-title">{title}</h2>
        <button type="button" className="modal-close" onClick={onClose} aria-label="Close">
          <Icon name="close"/>
        </button>
      </div>
      <div className="about-body pane-help-body">{children}</div>
    </div>
  </div>;
}
