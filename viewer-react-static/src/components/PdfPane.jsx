import {useEffect, useMemo, useRef, useState} from "react";
import * as pdfjs from "pdfjs-dist/legacy/build/pdf.mjs";
import PdfWorker from "pdfjs-dist/legacy/build/pdf.worker.min.mjs?worker";

pdfjs.GlobalWorkerOptions.workerPort = new PdfWorker();

/** Render one PDF page with clickable node-bbox overlays when enabled. */
export default function PdfPane({pdfUrl, page, highlight, pageNodes = [], overlayMode = "show", onNodeClick, onDocumentLoad}) {
  const host = useRef(null), canvas = useRef(null);
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
    const vp = pdfPage.getViewport({scale:Math.min(5, fitW)});
    setViewport(vp);
    const el = canvas.current;
    el.width = Math.ceil(vp.width); el.height = Math.ceil(vp.height);
    el.style.width = `${vp.width}px`; el.style.height = `${vp.height}px`;
    const task = pdfPage.render({canvasContext:el.getContext("2d"), viewport:vp});
    return () => task.cancel();
  }, [pdfPage, size]);

  const scale = useMemo(() => {
    if (!viewport) return null;
    // Cropped MediaBox: viewBox corners are raw PDF coords (crop origin 33,33),
    // so the visible size is the span, not the corner values.
    const width = viewport.viewBox[2] - viewport.viewBox[0];
    const height = viewport.viewBox[3] - viewport.viewBox[1];
    return {sx: viewport.width / width, sy: viewport.height / height};
  }, [viewport]);

  const boxes = useMemo(() => {
    if (!scale || !pageNodes.length) return [];
    return pageNodes.map((node) => {
      const [x0, y0, x1, y1] = node.bbox || [];
      return {
        node,
        x: x0 * scale.sx, y: y0 * scale.sy,
        width: Math.max(.6, (x1 - x0) * scale.sx), height: Math.max(.6, (y1 - y0) * scale.sy),
      };
    });
  }, [scale, pageNodes]);

  const selectionMark = useMemo(() => {
    if (!scale || !highlight?.bbox || highlight.page !== page) return null;
    const [x0, y0, x1, y1] = highlight.bbox;
    return {
      x: x0 * scale.sx, y: y0 * scale.sy,
      width: Math.max(.6, (x1 - x0) * scale.sx), height: Math.max(.6, (y1 - y0) * scale.sy),
    };
  }, [scale, highlight, page]);

  const clickable = overlayMode !== "off" && Boolean(onNodeClick);
  const visible = overlayMode === "show";

  return <div className="pdf-scroll" ref={host} aria-label="PDF page">
    {error && <div className="pdf-error">{error}</div>}
    <div className="page-stage">
      <canvas ref={canvas}/>
      {viewport && <svg className={`overlay ${clickable ? "clickable" : ""}`} width={viewport.width} height={viewport.height} viewBox={`0 0 ${viewport.width} ${viewport.height}`}>
        {visible && boxes.map((box) =>
          <rect key={box.node.id} className="box-tree-node" x={box.x} y={box.y} width={box.width} height={box.height}
                onClick={clickable ? () => onNodeClick(box.node) : undefined}>
            <title>{box.node.label || box.node.id}</title>
          </rect>)}
        {clickable && !visible && boxes.map((box) =>
          <rect key={box.node.id} className="box-tree-hit" x={box.x} y={box.y} width={box.width} height={box.height}
                fill="transparent" stroke="none"
                onClick={() => onNodeClick(box.node)}>
            <title>{box.node.label || box.node.id}</title>
          </rect>)}
        {selectionMark && <rect className="box-tree-node selected" x={selectionMark.x} y={selectionMark.y} width={selectionMark.width} height={selectionMark.height}>
          <title>{highlight.label || highlight.id}</title>
        </rect>}
      </svg>}
    </div>
  </div>;
}
