export const HIERARCHY_MODES = ["pdf", "prexc"];

export function hasDualHierarchy(tree) {
  return Boolean(tree?.hierarchy_modes?.length >= 2);
}

/** Parent id for the active hierarchy mode. */
export function parentId(node, mode) {
  if (mode === "prexc") return node.parent_prexc ?? node.parent ?? null;
  if (mode === "pdf") return node.parent_pdf ?? node.parent ?? null;
  return node.parent ?? null;
}

export function buildHierarchyIndex(nodes, mode) {
  const byId = new Map(nodes.map((node) => [node.id, node]));
  const children = new Map();
  const depth = new Map();

  for (const node of nodes) {
    const pid = parentId(node, mode);
    if (pid && byId.has(pid)) {
      if (!children.has(pid)) children.set(pid, []);
      children.get(pid).push(node.id);
    }
  }

  const getDepth = (id, seen = new Set()) => {
    if (depth.has(id)) return depth.get(id);
    if (seen.has(id)) return 0;
    seen.add(id);
    const node = byId.get(id);
    const pid = node ? parentId(node, mode) : null;
    const value = !pid || !byId.has(pid) ? 0 : getDepth(pid, seen) + 1;
    depth.set(id, value);
    return value;
  };
  for (const node of nodes) getDepth(node.id);

  return {byId, children, depth, parentIds: new Set(children.keys())};
}

export function isRowVisible(nodeId, byId, mode, expanded, included) {
  if (included && !included.has(nodeId)) return false;
  let cursor = byId.get(nodeId);
  while (cursor) {
    const pid = parentId(cursor, mode);
    if (!pid || !byId.has(pid)) break;
    if (!expanded.has(pid)) return false;
    cursor = byId.get(pid);
  }
  return true;
}

/**
 * Ancestor ids that must be expanded for `nodeIds` to be reachable.
 * Uses `parent` for legacy trees; dual-hierarchy trees pass `mode`.
 */
export function collectExpandAncestors(nodeIds, byId, {
  dualHierarchy = false,
  hierarchyMode = "prexc",
} = {}) {
  const ancestors = new Set();
  for (const id of nodeIds || []) {
    let cursor = byId.get(id);
    while (cursor) {
      const pid = dualHierarchy ? parentId(cursor, hierarchyMode) : cursor.parent;
      if (!pid || !byId.has(pid)) break;
      ancestors.add(pid);
      cursor = byId.get(pid);
    }
  }
  return ancestors;
}

/** Merge ancestor ids into an expanded set; returns `value` unchanged when already complete. */
export function withExpandedAncestors(value, ancestors) {
  let changed = false;
  for (const id of ancestors) {
    if (!value.has(id)) {
      changed = true;
      break;
    }
  }
  if (!changed) return value;
  const next = new Set(value);
  for (const id of ancestors) next.add(id);
  return next;
}

/** Document-order rows: fixed node sequence, depth from the chosen parent field. */
export function buildDocumentOrderRows(nodes, mode, expanded, included) {
  const {byId, children, depth} = buildHierarchyIndex(nodes, mode);
  const rows = [];
  for (const node of nodes) {
    if (!isRowVisible(node.id, byId, mode, expanded, included)) continue;
    rows.push({
      node,
      depth: depth.get(node.id) ?? 0,
      hasChildren: Boolean(children.get(node.id)?.length),
    });
  }
  return rows;
}
