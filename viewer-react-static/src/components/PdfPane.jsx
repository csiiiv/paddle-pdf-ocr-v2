import {useEffect, useMemo, useRef, useState} from "react";
import * as pdfjs from "pdfjs-dist/legacy/build/pdf.mjs";
import PdfWorker from "pdfjs-dist/legacy/build/pdf.worker.min.mjs?worker";

pdfjs.GlobalWorkerOptions.workerPort = new PdfWorker();

const toBox = (node, scale) => {
  const [x0, y0, x1, y1] = node.bbox || [];
  return {
    node,
    x: x0 * scale.sx,
    y: y0 * scale.sy,
    width: Math.max(.6, (x1 - x0) * scale.sx),
    height: Math.max(.6, (y1 - y0) * scale.sy),
  };
};

/** Among overlapping row strips, pick the box whose vertical center is closest. */
const pickBoxAt = (boxes, svgX, svgY) => {
  const hits = boxes.filter((box) =>
    svgX >= box.x && svgX <= box.x + box.width &&
    svgY >= box.y && svgY <= box.y + box.height);
  if (!hits.length) return null;
  hits.sort((left, right) => {
    const leftDist = Math.abs((left.y + left.height / 2) - svgY);
    const rightDist = Math.abs((right.y + right.height / 2) - svgY);
    if (leftDist !== rightDist) return leftDist - rightDist;
    // Tie-break: tighter (shorter) row, then smaller area.
    if (left.height !== right.height) return left.height - right.height;
    return (left.width * left.height) - (right.width * right.height);
  });
  return hits[0];
};

const touchDistance = (touches) => {
  if (touches.length < 2) return 0;
  const dx = touches[0].clientX - touches[1].clientX;
  const dy = touches[0].clientY - touches[1].clientY;
  return Math.hypot(dx, dy);
};

const pinchCenter = (touches, rect) => ({
  x: (touches[0].clientX + touches[1].clientX) / 2 - rect.left,
  y: (touches[0].clientY + touches[1].clientY) / 2 - rect.top,
});

/** Render one PDF page with clickable node-bbox overlays when enabled. */
export default function PdfPane({
  pdfUrl, page, highlight, pageNodes = [], overlayMode = "hide", zoom,
  onNodeClick, onDocumentLoad, onZoomChange, pinchZoom = false,
}) {
  const host = useRef(null), stage = useRef(null), canvas = useRef(null), svg = useRef(null);
  const fitScale = useRef({fitW:1, fitH:1});
  const pinch = useRef({active:false, startDist:0, startPercent:100, multiplier:1});
  const gesture = useRef({twoFinger:false, panning:false, blockClicksUntil:0});
  const zoomRef = useRef(zoom);
  zoomRef.current = zoom;
  const [pdf, setPdf] = useState(null), [pdfPage, setPdfPage] = useState(null);
  const [viewport, setViewport] = useState(null), [error, setError] = useState("");
  const [size, setSize] = useState({width:700, height:800});

  useEffect(() => {
    if (!host.current) return;
    const observer = new ResizeObserver(([entry]) => setSize({width:entry.contentRect.width, height:entry.contentRect.height}));
    observer.observe(host.current);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (!pdfUrl) { setPdf(null); setPdfPage(null); setViewport(null); return; }
    let live = true, task;
    setError("");
    (async () => {
      try {
        task = pdfjs.getDocument({url:pdfUrl, isEvalSupported:false, disableStream:true, disableAutoFetch:true, rangeChunkSize:65536});
        const doc = await task.promise;
        if (live) {
          setPdf(doc);
          onDocumentLoad?.(doc.numPages);
        }
      } catch (reason) {
        if (live) setError(`PDF failed to load. ${reason?.message || reason}`);
      }
    })();
    return () => { live = false; task?.destroy(); };
  }, [pdfUrl, onDocumentLoad]);

  useEffect(() => {
    if (!pdf || !page) { setPdfPage(null); return; }
    let live = true;
    pdf.getPage(page).then((value) => { if (live) setPdfPage(value); })
      .catch(() => { if (live) setPdfPage(null); });
    return () => { live = false; };
  }, [pdf, page]);

  useEffect(() => {
    if (!pdfPage || !canvas.current) return;
    const base = pdfPage.getViewport({scale:1});
    const fitW = Math.max(.25, (size.width - 28) / base.width);
    const fitH = Math.max(.25, (size.height - 28) / base.height);
    fitScale.current = {fitW, fitH};
    const mode = zoom?.mode || "fit";
    const percent = Number(zoom?.percent) || 100;
    const scale = mode === "height" ? fitH
      : fitW * (mode === "custom" ? Math.max(25, Math.min(400, percent)) / 100 : 1);
    const vp = pdfPage.getViewport({scale:Math.min(5, scale)});
    setViewport(vp);
    const el = canvas.current;
    el.width = Math.ceil(vp.width); el.height = Math.ceil(vp.height);
    el.style.width = `${vp.width}px`; el.style.height = `${vp.height}px`;
    const task = pdfPage.render({canvasContext:el.getContext("2d"), viewport:vp});
    // pdf.js rejects with RenderingCancelledException when a newer render
    // supersedes this one (page change, zoom, resize, Strict Mode remount).
    task.promise.catch((reason) => {
      if (reason?.name === "RenderingCancelledException") return;
      console.warn("PDF page render failed", reason);
    });
    return () => task.cancel();
  }, [pdfPage, size, zoom]);

  const effectivePercent = (value) => {
    const {fitW, fitH} = fitScale.current;
    if (value.mode === "custom") return value.percent;
    if (value.mode === "height") return (fitH / fitW) * 100;
    return 100;
  };

  // Pinch-to-zoom on touch devices; commit zoom on release.
  useEffect(() => {
    if (!pinchZoom || !onZoomChange) return;
    const scroll = host.current;
    if (!scroll) return;

    const blockClicks = (ms = 500) => {
      gesture.current.blockClicksUntil = Date.now() + ms;
    };
    const shouldBlockClicks = () => Date.now() < gesture.current.blockClicksUntil;

    const resetStageTransform = () => {
      const el = stage.current;
      if (!el) return;
      el.style.transform = "";
      el.style.transformOrigin = "";
    };

    const onTouchStart = (event) => {
      if (event.touches.length === 2) {
        gesture.current.twoFinger = true;
        gesture.current.panning = false;
        pinch.current = {
          active: true,
          startDist: touchDistance(event.touches),
          startPercent: effectivePercent(zoomRef.current),
          multiplier: 1,
        };
        return;
      }
      if (event.touches.length === 1) {
        gesture.current.panning = false;
        gesture.current.panStart = {
          x: event.touches[0].clientX,
          y: event.touches[0].clientY,
        };
      }
    };

    const onTouchMove = (event) => {
      if (pinch.current.active && event.touches.length >= 2) {
        event.preventDefault();
        gesture.current.twoFinger = true;
        const dist = touchDistance(event.touches);
        if (!pinch.current.startDist) return;
        const multiplier = dist / pinch.current.startDist;
        pinch.current.multiplier = multiplier;
        const el = stage.current;
        if (!el) return;
        const rect = el.getBoundingClientRect();
        const local = pinchCenter(event.touches, rect);
        el.style.transformOrigin = `${local.x}px ${local.y}px`;
        el.style.transform = `scale(${multiplier})`;
        return;
      }
      if (event.touches.length === 1 && gesture.current.panStart) {
        const dx = event.touches[0].clientX - gesture.current.panStart.x;
        const dy = event.touches[0].clientY - gesture.current.panStart.y;
        if (Math.hypot(dx, dy) > 8) gesture.current.panning = true;
      }
    };

    const finishTouch = (event) => {
      const hadPinch = pinch.current.active || gesture.current.twoFinger;

      if (pinch.current.active && event.touches.length < 2) {
        const {startPercent, multiplier} = pinch.current;
        pinch.current.active = false;
        resetStageTransform();
        if (Math.abs(multiplier - 1) > 0.02) {
          onZoomChange({
            mode: "custom",
            percent: Math.round(Math.max(25, Math.min(400, startPercent * multiplier))),
          });
        }
      }

      if (event.touches.length === 0) {
        if (hadPinch || gesture.current.panning) {
          blockClicks();
          event.preventDefault();
        }
        gesture.current.twoFinger = false;
        gesture.current.panning = false;
        gesture.current.panStart = null;
        return;
      }

      // Lifting one finger after a pinch — suppress the emulated click.
      if (hadPinch) {
        blockClicks();
        event.preventDefault();
      }
    };

    const swallowBlockedClick = (event) => {
      if (!shouldBlockClicks()) return;
      event.preventDefault();
      event.stopPropagation();
    };

    scroll.addEventListener("touchstart", onTouchStart, {passive: true});
    scroll.addEventListener("touchmove", onTouchMove, {passive: false});
    scroll.addEventListener("touchend", finishTouch, {passive: false});
    scroll.addEventListener("touchcancel", finishTouch, {passive: false});
    scroll.addEventListener("click", swallowBlockedClick, true);
    return () => {
      scroll.removeEventListener("touchstart", onTouchStart);
      scroll.removeEventListener("touchmove", onTouchMove);
      scroll.removeEventListener("touchend", finishTouch);
      scroll.removeEventListener("touchcancel", finishTouch);
      scroll.removeEventListener("click", swallowBlockedClick, true);
    };
  }, [pinchZoom, onZoomChange]);

  const scale = useMemo(() => {
    if (!viewport) return null;
    // Cropped MediaBox: viewBox corners are raw PDF coords (crop origin 33,33),
    // so the visible size is the span, not the corner values.
    const width = viewport.viewBox[2] - viewport.viewBox[0];
    const height = viewport.viewBox[3] - viewport.viewBox[1];
    return {sx: viewport.width / width, sy: viewport.height / height};
  }, [viewport]);

  // All row bboxes on this page (parents and leaves). Selected is painted last.
  const boxes = useMemo(() => {
    if (!scale) return [];
    const mapped = pageNodes.map((node) => toBox(node, scale));
    if (highlight?.bbox && Number(highlight.page) === Number(page) &&
        !mapped.some((box) => box.node.id === highlight.id)) {
      mapped.push(toBox(highlight, scale));
    }
    const selectedId = highlight?.id;
    mapped.sort((left, right) => {
      const leftSelected = left.node.id === selectedId ? 1 : 0;
      const rightSelected = right.node.id === selectedId ? 1 : 0;
      if (leftSelected !== rightSelected) return leftSelected - rightSelected;
      return left.y - right.y;
    });
    return mapped;
  }, [scale, pageNodes, highlight, page]);

  const clickable = overlayMode !== "off" && Boolean(onNodeClick);
  const visible = overlayMode === "show";

  const onOverlayClick = (event) => {
    if (!clickable || !svg.current) return;
    if (pinchZoom && Date.now() < gesture.current.blockClicksUntil) return;
    const point = svg.current.createSVGPoint();
    point.x = event.clientX;
    point.y = event.clientY;
    const local = point.matrixTransform(svg.current.getScreenCTM().inverse());
    const hit = pickBoxAt(boxes, local.x, local.y);
    if (hit) onNodeClick(hit.node);
  };

  return <div className={`pdf-scroll${pinchZoom ? " pdf-scroll-pinch" : ""}`} ref={host} aria-label="PDF page">
    {error && <div className="pdf-error">{error}</div>}
    <div className="page-stage" ref={stage}>
      <canvas ref={canvas}/>
      {viewport && <svg ref={svg} className={`overlay ${clickable ? "clickable" : ""}`}
                        width={viewport.width} height={viewport.height}
                        viewBox={`0 0 ${viewport.width} ${viewport.height}`}
                        onClick={clickable ? onOverlayClick : undefined}>
        {clickable && <rect className="box-tree-catcher" x={0} y={0} width={viewport.width} height={viewport.height}/>}
        {boxes.map((box) => {
          const selected = highlight?.id === box.node.id;
          if (!visible && !selected) return null;
          return <rect key={box.node.id} className={`box-tree-node ${selected ? "selected" : ""}`}
                       x={box.x} y={box.y} width={box.width} height={box.height}>
            <title>{box.node.label || box.node.id}</title>
          </rect>;
        })}
      </svg>}
    </div>
  </div>;
}
