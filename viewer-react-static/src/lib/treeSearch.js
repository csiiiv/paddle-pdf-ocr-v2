import {parentId} from "./treeHierarchy.js";
import {nodeSearchText} from "./treeLabelDisplay.js";

/** Nodes visible under the active tree search (matches plus ancestor chain). */
export function buildSearchIncluded(nodes, {
  query = "",
  currentOnly = false,
  currentPage = null,
  hierarchyMode = "prexc",
  dualHierarchy = false,
} = {}) {
  const needle = String(query || "").trim().toLowerCase();
  if (!needle && !currentOnly) return null;
  const byId = new Map(nodes.map((node) => [node.id, node]));
  const visible = new Set();
  for (const node of nodes) {
    const haystack = nodeSearchText(node).toLowerCase();
    const matchesText = !needle || haystack.includes(needle);
    const matchesPage = !currentOnly || Number(node.page) === Number(currentPage);
    if (!matchesText || !matchesPage) continue;
    let cursor = node;
    while (cursor) {
      visible.add(cursor.id);
      const pid = dualHierarchy ? parentId(cursor, hierarchyMode) : cursor.parent;
      cursor = pid ? byId.get(pid) : null;
    }
  }
  return visible;
}

export function isSearchFilterActive({query = "", currentOnly = false} = {}) {
  return Boolean(String(query || "").trim() || currentOnly);
}

export function isNodeInSearchResults(nodeId, included) {
  return included?.has(nodeId) ?? false;
}
