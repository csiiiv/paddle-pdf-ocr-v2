/** Format chainage / GPS anatomy as compact chip labels. */

export function formatChainageChip(span) {
  if (!span) return "";
  const kind = span.kind && span.kind !== "bare" ? `${span.kind} ` : "";
  const from = span.from ?? span.start ?? "";
  const to = span.to ?? span.end;
  return to ? `${kind}${from} → ${to}` : `${kind}${from}`;
}

export function formatGpsChip(coord) {
  if (!coord) return "";
  const lat = coord.lat;
  const lon = coord.lon;
  if (lat == null || lon == null) return coord.raw || "";
  const prefix = coord.role ? `${coord.role}: ` : "";
  return `${prefix}${Number(lat).toFixed(5)}, ${Number(lon).toFixed(5)}`;
}

export function nodeAnatomyChips(node) {
  const chainages = (node?.chainages || []).map(formatChainageChip).filter(Boolean);
  const coordinates = (node?.coordinates || []).map(formatGpsChip).filter(Boolean);
  return {chainages, coordinates};
}
