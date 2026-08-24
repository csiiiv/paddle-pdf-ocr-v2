/** Format PAP label anatomy for the tree table. */

import {formatChainageChip, formatGpsChip} from "./papLabelChips.js";

export {formatChainageChip, formatGpsChip};

export function nodeAnatomyChips(node) {
  const chainages = (node?.chainages || []).map(formatChainageChip).filter(Boolean);
  const coordinates = (node?.coordinates || []).map(formatGpsChip).filter(Boolean);
  return {chainages, coordinates};
}

export function nodeLabelTitle(node) {
  return node?.label || "";
}

export function nodeLabelDescription(node) {
  const description = (node?.description || "").trim();
  return description || null;
}

export function nodeLabelTooltip(node) {
  const ocr = (node?.label_ocr || "").trim();
  return ocr && ocr !== nodeLabelTitle(node) ? ocr : null;
}

/** Search haystack: title, code, kind, description, and anatomy text. */
export function nodeSearchText(node) {
  const {chainages, coordinates} = nodeAnatomyChips(node);
  return [
    node?.label,
    node?.code,
    node?.kind,
    node?.description,
    node?.label_ocr,
    ...chainages,
    ...coordinates,
  ].filter(Boolean).join(" ");
}
