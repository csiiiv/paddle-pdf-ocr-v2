import {useEffect,useRef,useState} from "react";
import SortableTable from "./SortableTable.jsx";
import TreePanel from "./TreePanel.jsx";
const PANELS=["tokens","lines","geometry","flags","sections","tree","pap","manifest","raw"];
export function PanelTabs({active,onChange}){return <nav className="panel-tabs">{PANELS.map((id)=><button key={id} className={active===id?"active":""} onClick={()=>onChange(id)}>{title(id)}</button>)}</nav>}
const title=(s)=>s==="pap"?"PAP":s[0].toUpperCase()+s.slice(1);

const TYPE_TO_PANEL={token:"tokens",line:"lines",band:"geometry",gap:"geometry",phrase:"geometry",column:"geometry",indent:"geometry",separator:"geometry",fit:"geometry",headerSection:"sections",columnSection:"sections",rowSection:"sections",cellSection:"sections",rowBoundary:"sections",reviewedBand:"sections",flag:"flags"};
export const panelForType=(type)=>TYPE_TO_PANEL[type]||null;
const PANEL_TYPES={tokens:["token"],lines:["line"],geometry:["band","gap","phrase","column","indent","separator","fit"],flags:["flag"],sections:["headerSection","columnSection","rowSection","cellSection","rowBoundary","reviewedBand"]};
export const panelShowsType=(panel,type)=>PANEL_TYPES[panel]?.includes(type)||false;

function useAutoScroll(host,selection,panel){
  useEffect(()=>{
    if(!selection?.type||!host.current)return;
    const row=host.current.querySelector(`tr[data-type="${selection.type}"][data-id="${String(selection.id)}"]`);
    row?.scrollIntoView?.({block:"nearest",behavior:"smooth"});
  },[selection,panel]);
}

function useFlagPageFocus(host,panel,currentPage,allLayers,showAll){
  useEffect(()=>{
    if(panel!=="flags"||!host.current)return;
    const row=host.current.querySelector(`tr[data-type="flag"][data-page="${currentPage}"]`);
    row?.scrollIntoView?.({block:"center",behavior:"smooth"});
    row?.focus?.({preventScroll:true});
  },[host,panel,currentPage,allLayers,showAll]);
}

function phraseLinks(phraseIds,item,geometry,allLayers,onSelect){
  if(!phraseIds?.length)return null;
  const page=item?.__page;
  const phrases=(page!=null?allLayers?.find((entry)=>entry.page===page)?.geometry:geometry)?.phrases;
  const byId=new Map((phrases||[]).map((phrase)=>[phrase.phrase_id,phrase]));
  return <span>{phraseIds.map((id,index)=><span key={id}>{index>0&&", "}<button className="link" onClick={(event)=>{event.stopPropagation();onSelect("phrase",id,{...(byId.get(id)||{phrase_id:id,text:`Phrase ${id}`}),...(page!=null?{__page:page}:{})})}}>{id}</button></span>)}</span>;
}

const pageRows=(allLayers,layer,key)=>allLayers.flatMap((entry)=>(entry[layer]?.[key]||[]).map((item,index)=>({...item,__page:entry.page,__rowIndex:index})));
const acrossPages=(data,headers,cells,showAll)=>showAll?{data,headers:["Page",...headers],cells:(item,index)=>[item.__page,...cells(item,item.__rowIndex??index)],idColumn:1}:{data,headers,cells,idColumn:0};

export default function Inspector({panel,layers,allLayers=[],showAll=false,manifest,tree,papTree,currentPage,selection,onSelect,flagFilter,onFlagFilter,onShowAll,flaggedPages=[]}){
  const host=useRef(null);
  useAutoScroll(host,selection,panel);
  useFlagPageFocus(host,panel,currentPage,allLayers,showAll);
  if(panel==="manifest")return <div ref={host}><pre>{JSON.stringify(manifest,null,2)}</pre></div>;
  if(panel==="raw")return <div ref={host}><pre>{JSON.stringify(layers,null,2)}</pre></div>;
  if(panel==="tree")return <div ref={host}><TreePanel tree={tree} stage="002.30" currentPage={currentPage} selection={selection} onSelect={onSelect}/></div>;
  if(panel==="pap")return <div ref={host}><TreePanel tree={papTree} stage="002.40" currentPage={currentPage} selection={selection} onSelect={onSelect}/></div>;
  if(panel==="flags")return <div ref={host}><Flags sections={layers.sections} geometry={layers.geometry} allLayers={allLayers} showAll={showAll} onShowAll={onShowAll} currentPage={currentPage} selection={selection} onSelect={onSelect} flagFilter={flagFilter} onFlagFilter={onFlagFilter} flaggedPages={flaggedPages}/></div>;
  if(panel==="sections")return <div ref={host}><Sections sections={layers.sections} reviewed={layers.reviewedTable} page={layers.geometry?.page} geometry={layers.geometry} allLayers={allLayers} showAll={showAll} selection={selection} onSelect={onSelect}/></div>;
  if(panel==="geometry")return <div ref={host}><Geometry geometry={layers.geometry} allLayers={allLayers} showAll={showAll} selection={selection} onSelect={onSelect}/></div>;
  const configs={
    tokens:{data:showAll?pageRows(allLayers,"paddle","tokens"):layers.paddle?.tokens,headers:["#","text","source","confidence","bbox"],type:"token",cells:(x,i)=>[x.__rowIndex??i,x.text,x.source,x.confidence,x.bbox?.join(", ")]},
    lines:{data:showAll?pageRows(allLayers,"paddle","lines"):layers.paddle?.lines,headers:["#","text","source","confidence","bbox"],type:"line",cells:(x,i)=>[x.line_id??i,x.text,x.source,x.confidence,x.bbox?.join(", ")]},
  };
  let config=configs[panel];if(config&&showAll)config={...config,...acrossPages(config.data,config.headers,config.cells,true)};if(!config?.data?.length)return <p className="muted">No {panel} artifact for this page.</p>;
  return <div ref={host}><DataTable {...config} selection={selection} onSelect={onSelect}/></div>;
}

function DataTable({data,headers,type,cells,idColumn=0,selection,onSelect,currentPage=null,initialSort=null}){
  return <SortableTable headers={headers} rows={data} cells={cells}
    initialSort={initialSort}
    rowKey={(item,index)=>`${type}-${cells(item,index)[idColumn]}-${item.__page??"page"}-${index}`}
    rowProps={(item,index)=>{const id=cells(item,index)[idColumn],selected=selection?.type===type&&String(selection.id)===String(id)&&(!item.__page||item.__page===selection.item?.__page),current=item.__page&&Number(item.__page)===Number(currentPage);return {"data-type":type,"data-id":id,"data-page":item.__page??null,tabIndex:-1,className:`${current?"current-page ":""}${selected?"selected":""}`.trim(),onClick:()=>onSelect(type,id,item)}}}/>;
}

function Geometry({geometry,allLayers,showAll,selection,onSelect}){
  const [active,setActive]=useState("bands");
  const sections=[
    ["bands","Bands","Baseline bands",geometry?.baseline_bands,["#","corrected baseline","raw baseline","confidence","local slope","tokens","bbox"],"band",(x,i)=>[x.band_id??i,x.baseline_y,x.raw_baseline_y,x.confidence,x.fit_slope,x.token_ids?.length,x.bbox?.join(", ")]],
    ["gaps","Gaps","Gaps",geometry?.gaps,["#","band","points","spaces","split","reason"],"gap",(x,i)=>[x.gap_id??i,x.band_id,x.gap_pt,x.estimated_spaces,String(x.split),x.reason]],
    ["phrases","Phrases","Phrases",geometry?.phrases,["#","band","observation","text type","text","edge","corrected x","anchor distance","reference","aligned amounts","lexical","context"],"phrase",(x,i)=>[x.phrase_id??i,x.band_id,x.observation,x.text_candidate_type,x.text,x.relative_anchor?.alignment_edge,x.relative_anchor?.corrected_x,x.relative_anchor?.distance_pt,x.relative_anchor?.reference_support,x.aligned_amount_phrase_ids?.join(", "),x.money_lexical_confidence,x.amount_context_confidence]],
    ["columns","Amount anchors","Amount right-edge anchors",geometry?.column_candidates,["#","right x","left envelope","drift","members","support","MAD","review"],"column",(x,i)=>[x.column_id??i,x.right_x,x.amount_left_x,x.drift_slope_dx_dy,x.n_phrases,x.support,x.right_mad,String(x.review)]],
    ["indents","Label indents","Label-indent anchors",geometry?.label_indent_anchors,["#","left x","members","support","MAD","review"],"indent",(x,i)=>[x.indent_id??i,x.left_x,x.n_phrases,x.support,x.left_mad,String(x.review)]],
    ["separators","Separators","Label/amount separator candidates",geometry?.separator_candidates,["#","band","label","amount","x","gap","review"],"separator",(x,i)=>[x.separator_id??i,x.band_id,x.label_phrase_id,x.amount_phrase_id,x.x,x.gap_pt,String(x.review)]],
    ["fits","Skew fits","Skew fits",geometry?.fit_candidates,["#","column","slope","MAD","pairs","review"],"fit",(x,i)=>[x.fit_id??i,x.column_id,x.slope,x.slope_mad,x.n_pairs,String(x.review)]],
  ];
  const typeTab={band:"bands",gap:"gaps",phrase:"phrases",column:"columns",indent:"indents",separator:"separators",fit:"fits"};
  useEffect(()=>{if(typeTab[selection?.type])setActive(typeTab[selection.type]);},[selection?.type]);
  if(!geometry)return <p className="muted">Stage 002.11 repaired token-geometry artifact missing.</p>;
  const current=sections.find(([id])=>id===active)||sections[0];
  const [id,,title,currentData,currentHeaders,type,currentCells]=current;
  const keys={bands:"baseline_bands",gaps:"gaps",phrases:"phrases",columns:"column_candidates",indents:"label_indent_anchors",separators:"separator_candidates",fits:"fit_candidates"};
  const table=acrossPages(showAll?pageRows(allLayers,"geometry",keys[id]):currentData,currentHeaders,currentCells,showAll);
  const count=(sectionId,items)=>showAll?pageRows(allLayers,"geometry",keys[sectionId]).length:items?.length??0;
  return <><div className="card"><strong>{geometry.algorithm?.name}</strong> · v{geometry.algorithm?.version}<br/><span className="muted">page baseline slope {geometry.diagnostics?.page_baseline_slope_dy_dx??"—"} · confidence {geometry.diagnostics?.page_baseline_slope_confidence??"—"} · {geometry.diagnostics?.page_baseline_slope_accepted?"accepted":"uncorrected"}</span></div><nav className="sub-tabs" aria-label="Geometry tables">{sections.map(([sectionId,label,,items])=><button key={sectionId} className={active===sectionId?"active":""} onClick={()=>setActive(sectionId)}>{label}<span>{count(sectionId,items)}</span></button>)}</nav><section className="geometry-section"><h3>{title}</h3>{table.data?.length?<DataTable {...table} type={type} selection={selection} onSelect={onSelect}/>:<p className="muted">No candidates.</p>}</section></>;
}

function Flags({sections:artifact,geometry,allLayers,showAll,onShowAll,currentPage,selection,onSelect,flagFilter,onFlagFilter,flaggedPages}){
  const setField=(key)=>(value)=>onFlagFilter?.((current)=>({...current,[key]:value}));
  const filterHint=[flagFilter?.includeOn&&`include ${flagFilter.include||"(empty)"}`,flagFilter?.excludeOn&&`exclude ${flagFilter.exclude||"(empty)"}`].filter(Boolean).join(" · ");
  const headers=["#","severity","code","object","message","phrases"];
  const cells=(x,i)=>[x.flag_id??i,x.severity,x.code,`${x.object_type}${x.object_id===null||x.object_id===undefined?"":` ${x.object_id}`}`,x.message,phraseLinks(x.phrase_ids,x,geometry,allLayers,onSelect)];
  const currentData=(artifact?.flagged_objects||[]).map((item,index)=>({...item,__page:currentPage,__rowIndex:index}));
  const table=acrossPages(showAll?pageRows(allLayers,"sections","flagged_objects"):currentData,headers,cells,showAll);
  return <>
    <div className="card flag-panel-controls">
      <div className="group flag-filters" title="Page ranges for Next flag counts and jumps (e.g. 13-20,106)">
        <Check label="All page data" checked={showAll} set={onShowAll}/>
        <Check label="Include" checked={!!flagFilter?.includeOn} set={setField("includeOn")}/>
        <input type="text" className="flag-range" placeholder="e.g. 13-20" value={flagFilter?.include||""} onChange={(e)=>setField("include")(e.target.value)} aria-label="Include page ranges"/>
        <Check label="Exclude" checked={!!flagFilter?.excludeOn} set={setField("excludeOn")}/>
        <input type="text" className="flag-range" placeholder="e.g. 15,18" value={flagFilter?.exclude||""} onChange={(e)=>setField("exclude")(e.target.value)} aria-label="Exclude page ranges"/>
      </div>
      <span className="muted">{flaggedPages?.length||0} flagged pages in scope</span>
    </div>
    <section className="geometry-section"><h3>Flagged objects</h3>{table.data?.length?<DataTable {...table} type="flag" currentPage={currentPage} initialSort={{column:0,direction:1}} selection={selection} onSelect={onSelect}/>:<p className="muted">No flagged objects{filterHint?` for ${filterHint}`:" across retained pages"}.</p>}</section>
  </>;
}

function Sections({sections:artifact,reviewed,page,geometry,allLayers,showAll,selection,onSelect}){
  const [active,setActive]=useState("headers");
  const reviewedRows=reviewedBands(reviewed,page);
  const sections=[
    ["headers","Headers","Header sections",artifact?.header_sections,["#","role","bands","text","phrases","bbox"],"headerSection",(x,i)=>[x.header_section_id??i,x.role,x.band_ids?.join(", "),x.text,x.phrase_ids?.length,x.bbox?.join(", ")]],
    ["columns","Columns","Column sections",artifact?.column_sections,["#","role","candidate","phrases","tokens","bbox"],"columnSection",(x,i)=>[x.column_section_id??i,x.role,x.source_column_candidate_id,x.phrase_ids?.length,x.source_token_ids?.length,x.bbox?.join(", ")]],
    ["boundaries","Row boundaries","Row boundaries",artifact?.row_boundaries,["#","kind","label phrase","amount phrases","observations","segment"],"rowBoundary",(x,i)=>[x.boundary_id??i,x.kind,x.label_phrase_id,x.amount_phrase_ids?.join(", "),x.n_observations,x.line_segment?.join(", ")]],
    ["rows","Rows","Row sections",artifact?.row_sections,["#","top","bottom","phrases","tokens","bbox"],"rowSection",(x,i)=>[x.row_section_id??i,x.top_boundary_id,x.bottom_boundary_id,x.phrase_ids?.length,x.source_token_ids?.length,x.bbox?.join(", ")]],
    ["cells","Cells","Cell sections",artifact?.cell_sections,["#","row","column","role","text","phrases","bbox"],"cellSection",(x,i)=>[x.cell_section_id??i,x.row_section_id,x.column_section_id,x.column_role,x.text,x.phrase_ids?.length,x.bbox?.join(", ")]],
    ["reviewed","Reviewed bands","Reviewed By-OU bands",reviewedRows,["role","band","source"],"reviewedBand",(x)=>[x.id,x.band_id,"fixtures/by_ou_table_seeds.json"]],
  ];
  const typeTab={headerSection:"headers",columnSection:"columns",rowBoundary:"boundaries",rowSection:"rows",cellSection:"cells",reviewedBand:"reviewed"};
  useEffect(()=>{if(typeTab[selection?.type])setActive(typeTab[selection.type]);},[selection?.type]);
  if(!artifact&&!reviewed)return <p className="muted">No section artifact or reviewed seed for this page.</p>;
  const current=sections.find(([id])=>id===active)||sections[0];
  const [id,,title,currentData,currentHeaders,type,currentCells]=current;
  const keys={headers:"header_sections",columns:"column_sections",boundaries:"row_boundaries",rows:"row_sections",cells:"cell_sections"};
  const reviewedAcross=()=>allLayers.flatMap((entry)=>reviewedBands(entry.reviewedTable,entry.page).map((item,index)=>({...item,__page:entry.page,__rowIndex:index})));
  const aggregate=id==="reviewed"?reviewedAcross():pageRows(allLayers,"sections",keys[id]);
  const table=acrossPages(showAll?aggregate:currentData,currentHeaders,currentCells,showAll);
  const count=(sectionId,items)=>showAll?(sectionId==="reviewed"?reviewedAcross().length:pageRows(allLayers,"sections",keys[sectionId]).length):items?.length??0;
  return <><div className="card"><strong>{artifact?.table_layout?.table_type||"unclassified"}</strong> · {artifact?.table_layout?.wrap_direction||"review"} · {artifact?.table_layout?.source||"no layout source"}{reviewed&&<><br/><span className="muted">{reviewed.table_id} · p.{reviewed.start.page} band {reviewed.start.body_first_band_id} → p.{reviewed.end.page} band {reviewed.end.terminal_band_id}</span></>}</div><nav className="sub-tabs" aria-label="Section tables">{sections.map(([sectionId,label,,items])=><button key={sectionId} className={active===sectionId?"active":""} onClick={()=>setActive(sectionId)}>{label}<span>{count(sectionId,items)}</span></button>)}</nav><section className="geometry-section"><h3>{title}</h3>{table.data?.length?<DataTable {...table} type={type} selection={selection} onSelect={onSelect}/>:<p className="muted">No candidates.</p>}</section></>;
}

function Check({label,checked,set}){return <label className="check"><input type="checkbox" checked={checked} onChange={(e)=>set(e.target.checked)}/>{label}</label>}

function reviewedBands(table,page){
  if(!table)return[];
  const rows=[];
  if(page===table.start.page){
    rows.push({role:"page_header",band_ids:table.start.page_header_band_ids||[]},{role:"table_title",band_ids:table.start.table_title_band_ids||[]},{role:"column_headers",band_ids:table.start.column_header_band_ids||[]},{role:"hierarchy_root",band_ids:[table.hierarchy_seed.band_id]});
  }else{
    const expectation=table.page_expectations?.find((item)=>item.page===page);
    if(expectation?.page_header_band_ids)rows.push({role:"page_header",band_ids:expectation.page_header_band_ids});
  }
  if(page===table.end.page)rows.push({role:"table_terminal",band_ids:[table.end.terminal_band_id]},{role:"next_table",band_ids:[table.end.next_table_first_band_id]});
  return rows.flatMap((row)=>row.band_ids.map((band_id)=>({id:`${row.role}:${band_id}`,role:row.role,band_id})));
}
