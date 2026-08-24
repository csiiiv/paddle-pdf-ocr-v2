import {useEffect, useMemo, useState} from "react";
import Icon from "./Icon.jsx";
import {
  buildDocumentOrderRows,
  buildHierarchyIndex,
  hasDualHierarchy,
  parentId,
} from "../lib/treeHierarchy.js";
import {DEFAULT_HIERARCHY} from "../lib/viewState.js";
import {useResizableColumns} from "../lib/useResizableColumns.js";
import {colGripGutter, colWidth} from "../lib/treeTableLayout.js";
import {
  nodeAnatomyChips,
  nodeLabelDescription,
  nodeLabelTitle,
  nodeLabelTooltip,
} from "../lib/treeLabelDisplay.js";
import {buildSearchIncluded, isSearchFilterActive} from "../lib/treeSearch.js";

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

const amountColumnKey = (role) => `amount:${role}`;

function ResizeHeader({columnKey, className, children, width, compact, active, onResizeStart}) {
  return <th className={`tree-th-resizable${className ? ` ${className}` : ""}`} style={{width}}>
    <div className="tree-th-layout">
      <div className="tree-col-head">{children}</div>
      <div className="tree-col-gutter">
        <button type="button"
                className={`col-resize-grip${active ? " is-active" : ""}${compact ? " is-compact" : ""}`}
                aria-label="Drag to resize column"
                onPointerDown={(event) => onResizeStart(columnKey, event)}>
          <Icon name="arrows_outward" size={compact ? 16 : 14}/>
        </button>
      </div>
    </div>
  </th>;
}

/** Searchable, collapsible hierarchy table over a slim exported tree. */
export default function TreePanel({
  tree, currentPage, selectedId, onSelect, compact = false, active = true,
  hierarchyMode = DEFAULT_HIERARCHY, onHierarchyModeChange, onOpenHelp,
  onSearchFilterChange,
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

  const included = useMemo(
    () => buildSearchIncluded(nodes, {
      query,
      currentOnly,
      currentPage,
      hierarchyMode,
      dualHierarchy,
    }),
    [query, currentOnly, currentPage, nodes, dualHierarchy, hierarchyMode],
  );

  useEffect(() => {
    onSearchFilterChange?.({
      active: isSearchFilterActive({query, currentOnly}),
      included,
    });
  }, [query, currentOnly, included, onSearchFilterChange]);

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

  const amountColumns = useMemo(
    () => (tree ? (tree.columns || collectAmountColumns(nodes)) : []),
    [tree, nodes],
  );
  const columnDefs = useMemo(() => {
    const gutter = colGripGutter(compact);
    return [
      {key: "kind", default: colWidth(compact ? 96 : 110, compact), min: colWidth(72, compact), gutter},
      {key: "page", default: colWidth(compact ? 48 : 55, compact), min: colWidth(44, compact), gutter},
      {key: "label", default: colWidth(compact ? 280 : 360, compact), min: colWidth(160, compact), gutter},
      ...amountColumns.map((role) => ({
        key: amountColumnKey(role),
        default: colWidth(compact ? 104 : 120, compact),
        min: colWidth(72, compact),
        gutter,
      })),
    ];
  }, [amountColumns, compact]);
  const {widths, startResize, totalWidth, resizingKey} = useResizableColumns(columnDefs);

  if (!tree) return <p className="muted">No tree loaded.</p>;

  const select = (node) => onSelect(node);

  const hierarchySelect = dualHierarchy &&
    <select className="tree-hierarchy-select" aria-label="Hierarchy level"
            value={hierarchyMode}
            onChange={(event) => onHierarchyModeChange?.(event.target.value)}>
      {hierarchyOptions.map((option) =>
        <option key={option.value} value={option.value}>{option.label}</option>)}
    </select>;

  return <div className={`tree-panel${compact ? " is-compact" : ""}`}
              style={{"--col-grip-gutter": `${colGripGutter(compact)}px`}}>
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
      {onOpenHelp &&
        <button type="button" className="pane-info-btn" onClick={onOpenHelp} aria-label="Data pane help">
          <Icon name="info"/>
        </button>}
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
        <table className="tree-table" style={{width: Math.max(totalWidth, 720)}}>
          <colgroup>
            {columnDefs.map((column) =>
              <col key={column.key} style={{width: widths[column.key]}}/>)}
          </colgroup>
          <thead><tr>
            <ResizeHeader columnKey="kind" className="tree-kind-col" width={widths.kind}
                          compact={compact} active={resizingKey === "kind"} onResizeStart={startResize}>
              Kind
            </ResizeHeader>
            <ResizeHeader columnKey="page" className="tree-page-col" width={widths.page}
                          compact={compact} active={resizingKey === "page"} onResizeStart={startResize}>
              Page
            </ResizeHeader>
            <ResizeHeader columnKey="label" className="tree-label-col" width={widths.label} compact={compact}
                          active={resizingKey === "label"} onResizeStart={startResize}>
              <div className="tree-hierarchy-head">
                <span>Hierarchy label</span>
                {!compact && hierarchySelect}
              </div>
            </ResizeHeader>
            {amountColumns.map((role) => {
              const columnKey = amountColumnKey(role);
              return <ResizeHeader key={role} columnKey={columnKey} className="tree-amount-col"
                                   width={widths[columnKey]} compact={compact}
                                   active={resizingKey === columnKey} onResizeStart={startResize}>
                {role}
              </ResizeHeader>;
            })}
          </tr></thead>
          <tbody>{rows.map(({node, depth, hasChildren}) => {
            const selected = selectedId === node.id;
            const {chainages, coordinates} = nodeAnatomyChips(node);
            const title = nodeLabelTitle(node);
            const description = nodeLabelDescription(node);
            const tooltip = nodeLabelTooltip(node);
            return <tr key={node.id} data-node-id={node.id} className={`${node.page === currentPage ? "current-page " : ""}${selected ? "selected" : ""}`} onClick={() => select(node)}>
              <td className="tree-kind">{kindLabel(node.kind)}</td>
              <td className="tree-page-col">{node.page ? <button className="link" onClick={(event) => {event.stopPropagation(); select(node)}}>p.{node.page}</button> : "—"}</td>
              <td className="tree-label-col">
                <div className="tree-label" style={{"--tree-depth":depth}}>
                  {hasChildren
                    ? <button className="tree-toggle" aria-label={`${expanded.has(node.id) ? "Collapse" : "Expand"} ${node.label}`} aria-expanded={expanded.has(node.id)} onClick={(event) => {event.stopPropagation(); toggle(node.id)}}>
                        <Icon name={expanded.has(node.id) ? "expand_more" : "chevron_right"} size={18}/>
                      </button>
                    : <span className="tree-spacer"/>}
                  <span className="tree-label-body">
                    <span className="tree-label-text" title={tooltip || undefined}>
                      <span className={`tree-kind-dot kind-${node.kind}`}/>{title || "(blank label)"}{node.code && <code>{node.code}</code>}
                    </span>
                    {description &&
                      <span className="tree-label-description">{description}</span>}
                    {(chainages.length > 0 || coordinates.length > 0) &&
                      <span className="tree-label-chips">
                        {chainages.map((text, index) =>
                          <span key={`${node.id}:ch:${index}`} className="label-chip label-chip-chainage">{text}</span>)}
                        {coordinates.map((text, index) =>
                          <span key={`${node.id}:gps:${index}`} className="label-chip label-chip-gps">{text}</span>)}
                      </span>}
                  </span>
                </div>
              </td>
              {amountColumns.map((role) => <td key={role} className="tree-amount">{formatAmountCell(node, role) || "—"}</td>)}
            </tr>;
          })}</tbody>
        </table>
      </div>}
  </div>;
}
