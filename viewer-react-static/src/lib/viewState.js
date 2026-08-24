export const DEFAULT_ZOOM = {mode:"fit", percent:100};
export const DEFAULT_SPLIT = 58;
export const OVERLAY_MODES = ["show","hide","off"];

const CUSTOM_ZOOM = "custom,";

const bounded = (value, min, max, fallback) => {
  if (value === null || value === undefined || value === "") return fallback;
  const n = Number(value);
  return Number.isFinite(n) ? Math.min(max, Math.max(min, n)) : fallback;
};

/** Parse shareable view state: ?doc=&tree=&page=&node=&zoom=&split=&overlay= */
export function parseView(params) {
  const zoomParam = params.get("zoom");
  let zoom = DEFAULT_ZOOM;
  if (zoomParam === "fit" || zoomParam === "height") zoom = {mode:zoomParam, percent:100};
  else if (zoomParam?.startsWith(CUSTOM_ZOOM)) zoom = {mode:"custom", percent:bounded(zoomParam.slice(CUSTOM_ZOOM.length),25,400,100)};
  const overlayParam = params.get("overlay");
  return {
    doc: params.get("doc") || "",
    tree: params.get("tree") || "",
    page: bounded(params.get("page"), 1, 100000, null),
    node: params.get("node") || "",
    zoom,
    split: bounded(params.get("split"), 32, 76, DEFAULT_SPLIT),
    overlay: OVERLAY_MODES.includes(overlayParam) ? overlayParam : "show",
  };
}

export function writeView(params, {doc, tree, page, node, zoom, split, overlay}) {
  const setValue = (key, value, fallback) => {
    if (value === undefined || value === null || value === "" || value === fallback) params.delete(key);
    else params.set(key, value);
  };
  setValue("doc", doc, "");
  setValue("tree", tree, "");
  setValue("page", page, null);
  setValue("node", node, "");
  const zoomValue = zoom.mode === "custom" ? `${CUSTOM_ZOOM}${zoom.percent}` : zoom.mode;
  if (zoomValue === DEFAULT_ZOOM.mode) params.delete("zoom"); else params.set("zoom", zoomValue);
  if (split === DEFAULT_SPLIT) params.delete("split"); else params.set("split", split);
  setValue("overlay", overlay, "show");
  return params;
}
