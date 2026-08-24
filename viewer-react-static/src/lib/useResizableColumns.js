import {useCallback, useEffect, useMemo, useState} from "react";

/** Track resizable table column widths (pointer + touch via setPointerCapture). */
export function useResizableColumns(columns) {
  const [widths, setWidths] = useState(() =>
    Object.fromEntries(columns.map((column) => [column.key, column.default])));
  const [resizingKey, setResizingKey] = useState(null);

  useEffect(() => {
    setWidths((previous) => {
      let changed = false;
      const next = {...previous};
      for (const column of columns) {
        if (!(column.key in next)) {
          next[column.key] = column.default;
          changed = true;
        }
      }
      return changed ? next : previous;
    });
  }, [columns]);

  const startResize = useCallback((key, event) => {
    event.preventDefault();
    event.stopPropagation();
    const column = columns.find((entry) => entry.key === key);
    if (!column) return;

    const handle = event.currentTarget;
    handle.setPointerCapture(event.pointerId);
    document.body.classList.add("col-resizing");
    setResizingKey(key);

    const startX = event.clientX;
    const startWidth = widths[key] ?? column.default;

    const onMove = (moveEvent) => {
      if (moveEvent.pointerId !== event.pointerId) return;
      const delta = moveEvent.clientX - startX;
      setWidths((previous) => ({
        ...previous,
        [key]: Math.max(column.min, startWidth + delta),
      }));
    };

    const onEnd = (endEvent) => {
      if (endEvent.pointerId !== event.pointerId) return;
      handle.releasePointerCapture(event.pointerId);
      handle.removeEventListener("pointermove", onMove);
      handle.removeEventListener("pointerup", onEnd);
      handle.removeEventListener("pointercancel", onEnd);
      document.body.classList.remove("col-resizing");
      setResizingKey(null);
    };

    handle.addEventListener("pointermove", onMove);
    handle.addEventListener("pointerup", onEnd);
    handle.addEventListener("pointercancel", onEnd);
  }, [columns, widths]);

  const totalWidth = useMemo(
    () => columns.reduce((sum, column) => sum + (widths[column.key] ?? column.default), 0),
    [columns, widths],
  );

  return {widths, startResize, totalWidth, resizingKey};
}
