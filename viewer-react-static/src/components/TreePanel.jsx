import {useEffect, useMemo, useState} from "react";
import Icon from "./Icon.jsx";
import {
  buildDocumentOrderRows,
  buildHierarchyIndex,
  hasDualHierarchy,
  parentId,
} from "../lib/treeHierarchy.js";
import {DEFAULT_HIERARCHY} from "../lib/viewState.js";

const KNOWN_AMOUNT_ORDER = ["PS","MOOE","CO"];

const amountColumnRank = (role) => {
  const known = KNOWN_AMOUNT_ORDER.indexOf(role);
  if (known >= 0) return known;
  if (role === "Total") return 10000;
  const match = /^Amount\s+(\d+)$/i.exec(role);
  if (match) return 100 + Number(match[1]);
  return 1000;
};

const sortAmountColumns = (keys) => [...keys].sort((left, right) => {
  const rank = amountColumnRank(left) - amountColumnRank(right);
  return rank !== 0 ? rank : left.localeCompare(right);
});

const collectAmountColumns = (nodes) => {
  const keys = new Set();
  for (const node of nodes) {
    for (const key of Object.keys(node.amounts || {})) keys.add(key);
    if (node.total?.role && node.total?.text) keys.add(node.total.role);
  }
  return sortAmountColumns([...keys]);
};

const formatAmountCell = (node, role) => node?.amounts?.[role]?.text
  || (node?.total?.role === role ? node.total.text : "");
const kindLabel = (kind) => String(kind || "").replaceAll("_", " ");

const hierarchyOptions = [
  {value: "prexc", label: "PREXC code"},
  {value: "pdf", label: "PDF layout"},
];

/** Searchable, collapsible hierarchy table over a slim exported tree. */
export default function TreePanel({
  tree, currentPage, selectedId, onSelect, compact = false, active = true,
  hierarchyMode = DEFAULT_HIERARCHY, onHierarchyModeChange,
}) {
  const nodes = tree?.nodes || [];
  const dualHierarchy = hasDualHierarchy(tree);
  const byId = useMemo(() => new Map(nodes.map((node) => [node.id, node])), [nodes]);
  const hierarchyIndex = useMemo(
    () => (dualHierarchy ? buildHierarchyIndex(nodes, hierarchyMode) : null),
    [nodes, hierarchyMode, dualHierarchy],
  );
  const parentIds = useMemo(() => {
    if (dualHierarchy) return hierarchyIndex.parentIds;
    return new Set(nodes.filter((node) => node.children?.length).map((node) => node.id));
  }, [nodes, hierarchyIndex, dualHierarchy]);
  const [expanded, setExpanded] = useState(() => new Set(tree?.roots || []));
  const [queryDraft, setQueryDraft] = useState("");
  const [query, setQuery] = useState("");
  const [currentOnly, setCurrentOnly] = useState(false);

  useEffect(() => {
    setExpanded(new Set(tree?.roots || []));
  }, [tree?.id, hierarchyMode]);

  // Debounce search so large trees don't refilter on every keystroke.
  useEffect(() => {
    const timer = setTimeout(() => setQuery(queryDraft), 250);
    return () => clearTimeout(timer);
  }, [queryDraft]);

  // Reveal the selected row: expand only its ancestor chain (never the node
  // itself, so its own children stay collapsed) and scroll it into view.
  // Wait until the pane is visible (mobile Data tab) so scrollIntoView works.
  useEffect(() => {
    if (!selectedId || !tree || !active) return;
    setExpanded((value) => {
      const next = new Set(value);
      let cursor = byId.get(selectedId);
      while (cursor) {
        const pid = dualHierarchy ? parentId(cursor, hierarchyMode) : cursor.parent;
        if (!pid) break;
        next.add(pid);
        cursor = byId.get(pid);
      }
      return next;
    });
    const frame = requestAnimationFrame(() => {
      document.querySelector(`tr[data-node-id="${CSS.escape(selectedId)}"]`)
        ?.scrollIntoView({block: "nearest"});
    });
    return () => cancelAnimationFrame(frame);
  }, [selectedId, tree, byId, active, dualHierarchy, hierarchyMode]);

  const included = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle && !currentOnly) return null;
    const visible = new Set();
    for (const node of nodes) {
      const matchesText = !needle || `${node.label || ""} ${node.code || ""} ${node.kind || ""}`.toLowerCase().includes(needle);
      const matchesPage = !currentOnly || node.page === currentPage;
      if (!matchesText || !matchesPage) continue;
      let cursor = node;
      while (cursor) {
        visible.add(cursor.id);
        const pid = dualHierarchy ? parentId(cursor, hierarchyMode) : cursor.parent;
        cursor = pid ? byId.get(pid) : null;
      }
    }
    return visible;
  }, [query, currentOnly, currentPage, nodes, byId, dualHierarchy, hierarchyMode]);

  const toggle = (id) => setExpanded((value) => {
    const next = new Set(value);
    if (next.has(id)) next.delete(id); else next.add(id);
    return next;
  });

  const rows = useMemo(() => {
    if (dualHierarchy) {
      return buildDocumentOrderRows(nodes, hierarchyMode, expanded, included);
    }
    const legacy = [];
    const visit = (id, depth) => {
      const node = byId.get(id);
      if (!node || included && !included.has(id)) return;
      legacy.push({node, depth, hasChildren: Boolean(node.children?.length)});
      if ((expanded.has(id) || included) && node.children?.length) {
        node.children.forEach((child) => visit(child, depth + 1));
      }
    };
    (tree?.roots || []).forEach((id) => visit(id, 0));
    return legacy;
  }, [dualHierarchy, nodes, hierarchyMode, expanded, included, byId, tree?.roots]);

  if (!tree) return <p className="muted">No tree loaded.</p>;

  const amountColumns = tree.columns || collectAmountColumns(nodes);
  const select = (node) => onSelect(node);

  const hierarchySelect = dualHierarchy &&
    <select className="tree-hierarchy-select" aria-label="Hierarchy level"
            value={hierarchyMode}
            onChange={(event) => onHierarchyModeChange?.(event.target.value)}>
      {hierarchyOptions.map((option) =>
        <option key={option.value} value={option.value}>{option.label}</option>)}
    </select>;

  return <div className={`tree-panel${compact ? " is-compact" : ""}`}>
    {!compact &&
      <div className="card tree-summary">
        <div><strong>{tree.title || tree.id || "Tree"}</strong><br/>
          <span className="muted">{nodes.length} nodes · {tree.pages?.length ?? new Set(nodes.map((n) => n.page).filter(Boolean)).size} pages</span>
        </div>
        <div className="tree-actions">
          <button type="button" onClick={() => setExpanded(new Set(parentIds))}>Expand all</button>
          <button type="button" onClick={() => setExpanded(new Set(tree.roots || []))}>Collapse</button>
        </div>
      </div>}
    <div className="tree-toolbar">
      {compact && hierarchySelect}
      <input aria-label="Search tree" type="search" placeholder={compact ? "Search…" : "Search label, code, or kind…"} value={queryDraft} onChange={(event) => setQueryDraft(event.target.value)}/>
      <label className="check"><input type="checkbox" checked={currentOnly} onChange={(event) => setCurrentOnly(event.target.checked)}/>{compact ? `p.${currentPage ?? "—"}` : `Page ${currentPage} only`}</label>
      {!compact && <span className="muted">{rows.length} visible</span>}
      {compact &&
        <div className="tree-actions">
          <button type="button" onClick={() => setExpanded(new Set(parentIds))}>Expand</button>
          <button type="button" onClick={() => setExpanded(new Set(tree.roots || []))}>Collapse</button>
        </div>}
    </div>
    {!rows.length ? <p className="muted">No matching hierarchy rows.</p> :
      <div className="tree-table-wrap">
        <table className="tree-table">
          <thead><tr>
            <th>
              <div className="tree-hierarchy-head">
                <span>Hierarchy label</span>
                {!compact && hierarchySelect}
              </div>
            </th>
            <th>Kind</th><th>Page</th>
            {amountColumns.map((role) => <th key={role} className="tree-amount-col">{role}</th>)}
          </tr></thead>
          <tbody>{rows.map(({node, depth, hasChildren}) => {
            const selected = selectedId === node.id;
            return <tr key={node.id} data-node-id={node.id} className={`${node.page === currentPage ? "current-page " : ""}${selected ? "selected" : ""}`} onClick={() => select(node)}>
              <td>
                <div className="tree-label" style={{"--tree-depth":depth}}>
                  {hasChildren
                    ? <button className="tree-toggle" aria-label={`${expanded.has(node.id) ? "Collapse" : "Expand"} ${node.label}`} aria-expanded={expanded.has(node.id)} onClick={(event) => {event.stopPropagation(); toggle(node.id)}}>
                        <Icon name={expanded.has(node.id) ? "expand_more" : "chevron_right"} size={18}/>
                      </button>
                    : <span className="tree-spacer"/>}
                  <span><span className={`tree-kind-dot kind-${node.kind}`}/>{node.label || "(blank label)"}{node.code && <code>{node.code}</code>}</span>
                </div>
              </td>
              <td className="tree-kind">{kindLabel(node.kind)}</td>
              <td>{node.page ? <button className="link" onClick={(event) => {event.stopPropagation(); select(node)}}>p.{node.page}</button> : "—"}</td>
              {amountColumns.map((role) => <td key={role} className="tree-amount">{formatAmountCell(node, role) || "—"}</td>)}
            </tr>;
          })}</tbody>
        </table>
      </div>}
  </div>;
}
