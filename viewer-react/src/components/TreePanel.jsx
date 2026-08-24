import {useEffect,useMemo,useState} from "react";

const KNOWN_AMOUNT_ORDER=["PS","MOOE","CO"];

const amountColumnRank=(role)=>{
  const known=KNOWN_AMOUNT_ORDER.indexOf(role);
  if(known>=0)return known;
  if(role==="Total")return 10000;
  const match=/^Amount\s+(\d+)$/i.exec(role);
  if(match)return 100+Number(match[1]);
  return 1000;
};

const sortAmountColumns=(keys)=>[...keys].sort((left,right)=>{
  const rank=amountColumnRank(left)-amountColumnRank(right);
  return rank!==0?rank:left.localeCompare(right);
});

const collectAmountColumns=(nodes)=>{
  const keys=new Set();
  for(const node of nodes){
    for(const key of Object.keys(node.amounts||{}))keys.add(key);
    if(node.total?.role)keys.add(node.total.role);
  }
  return sortAmountColumns([...keys]);
};

const formatAmountCell=(node,role)=>node?.amounts?.[role]?.text
  ||(node?.total?.role===role?node.total.text:"");
const kindLabel=(kind)=>String(kind||"").replaceAll("_"," ");

export default function TreePanel({tree,stage="002.30",currentPage,selection,onSelect}){
  const nodes=tree?.nodes||[];
  const byId=useMemo(()=>new Map(nodes.map((node)=>[node.id,node])),[nodes]);
  const parentIds=useMemo(()=>new Set(nodes.filter((node)=>node.children?.length).map((node)=>node.id)),[nodes]);
  const amountColumns=useMemo(()=>collectAmountColumns(nodes),[nodes]);
  const [expanded,setExpanded]=useState(()=>new Set(tree?.roots||[]));
  const [query,setQuery]=useState("");
  const [currentOnly,setCurrentOnly]=useState(false);

  useEffect(()=>{
    if(!nodes.length)return;
    const next=new Set(tree?.roots||[]);
    for(const node of nodes){
      if(node.page!==currentPage)continue;
      let cursor=node;
      while(cursor?.parent){
        next.add(cursor.parent);
        cursor=byId.get(cursor.parent);
      }
    }
    setExpanded((value)=>new Set([...value,...next]));
  },[tree,currentPage,byId,nodes.length]);

  const included=useMemo(()=>{
    const needle=query.trim().toLowerCase();
    if(!needle&&!currentOnly)return null;
    const visible=new Set();
    for(const node of nodes){
      const matchesText=!needle||`${node.label||""} ${node.code||""} ${node.kind||""}`.toLowerCase().includes(needle);
      const matchesPage=!currentOnly||node.page===currentPage;
      if(!matchesText||!matchesPage)continue;
      let cursor=node;
      while(cursor){
        visible.add(cursor.id);
        cursor=cursor.parent?byId.get(cursor.parent):null;
      }
    }
    return visible;
  },[query,currentOnly,currentPage,nodes,byId]);

  const toggle=(id)=>setExpanded((value)=>{
    const next=new Set(value);
    if(next.has(id))next.delete(id);else next.add(id);
    return next;
  });
  const collapseChildBranches=(node)=>{
    setExpanded((value)=>{
      const next=new Set(value);
      next.add(node.id);
      node.children?.forEach((child)=>next.delete(child));
      return next;
    });
  };
  const rows=[];
  const visit=(id,depth)=>{
    const node=byId.get(id);
    if(!node||included&&!included.has(id))return;
    rows.push({node,depth});
    if((expanded.has(id)||included)&&node.children?.length)
      node.children.forEach((child)=>visit(child,depth+1));
  };
  (tree?.roots||[]).forEach((id)=>visit(id,0));

  if(!tree)return <p className="muted">No hierarchy tree artifact. Run stage {stage} for the desired pages.</p>;
  const diagnostics=tree.diagnostics||{};
  const select=(node)=>{
    if(node.page==null)return;
    onSelect("treeNode",node.id,{...node,__page:node.page});
  };
  return <div className="tree-panel">
    <div className="card tree-summary">
      <div><strong>{tree.table?.title||tree.table?.table_id||"By-OU table"}</strong><br/>
        <span className="muted">{diagnostics.n_nodes??nodes.length} nodes · {diagnostics.n_pages??tree.table?.requested_pages?.length??0} pages · {diagnostics.n_review_flags??0} review flags</span>
      </div>
      <div className="tree-actions">
        <button onClick={()=>setExpanded(new Set(parentIds))}>Expand all</button>
        <button onClick={()=>setExpanded(new Set(tree.roots||[]))}>Collapse</button>
      </div>
    </div>
    <div className="tree-toolbar">
      <input aria-label="Search tree" type="search" placeholder="Search label, code, or kind…" value={query} onChange={(event)=>setQuery(event.target.value)}/>
      <label className="check"><input type="checkbox" checked={currentOnly} onChange={(event)=>setCurrentOnly(event.target.checked)}/>Page {currentPage} only</label>
      <span className="muted">{rows.length} visible</span>
    </div>
    {!rows.length?<p className="muted">No matching hierarchy rows.</p>:
      <div className="tree-table-wrap">
      <table className="tree-table">
        <thead><tr><th>Hierarchy label</th><th>Kind</th><th>Page</th>
          {amountColumns.map((role)=><th key={role} className="tree-amount-col">{role}</th>)}
        </tr></thead>
        <tbody>{rows.map(({node,depth})=>{
          const hasChildren=Boolean(node.children?.length);
          const hasChildBranches=node.children?.some((child)=>byId.get(child)?.children?.length);
          const selected=selection?.type==="treeNode"&&String(selection.id)===String(node.id);
          return <tr key={node.id} className={`${node.page===currentPage?"current-page ":""}${selected?"selected":""}`} data-node-id={node.id} onClick={()=>select(node)}>
            <td>
              <div className="tree-label" style={{"--tree-depth":depth}}>
                {hasChildren?<button className="tree-toggle" aria-label={`${expanded.has(node.id)?"Collapse":"Expand"} ${node.label}`} aria-expanded={expanded.has(node.id)} onClick={(event)=>{event.stopPropagation();toggle(node.id)}}>{expanded.has(node.id)?"▾":"▸"}</button>:<span className="tree-spacer"/>}
                {hasChildBranches?<button className="tree-collapse-children" aria-label={`Collapse child branches of ${node.label}`} title="Collapse immediate child branches" onClick={(event)=>{event.stopPropagation();collapseChildBranches(node)}}>⊟</button>:<span className="tree-child-action-spacer"/>}
                <span><span className={`tree-kind-dot kind-${node.kind}`}/>{node.label||"(blank label)"}{node.code&&<code>{node.code}</code>}{node.flags?.length>0&&<span className="tree-flag" title={node.flags.join(", ")}>!</span>}</span>
              </div>
            </td>
            <td className="tree-kind">{kindLabel(node.kind)}</td>
            <td>{node.page?<button className="link" onClick={(event)=>{event.stopPropagation();select(node)}}>p.{node.page}</button>:"—"}</td>
            {amountColumns.map((role)=><td key={role} className="tree-amount">{formatAmountCell(node,role)||"—"}</td>)}
          </tr>;
        })}</tbody>
      </table>
      </div>}
  </div>;
}
