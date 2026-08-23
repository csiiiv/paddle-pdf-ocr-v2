import {useEffect,useRef} from "react";
const PANELS=["tokens","lines","geometry","zones","schema","manifest","raw"];
export function PanelTabs({active,onChange}){return <nav className="panel-tabs">{PANELS.map((id)=><button key={id} className={active===id?"active":""} onClick={()=>onChange(id)}>{title(id)}</button>)}</nav>}
const title=(s)=>s[0].toUpperCase()+s.slice(1);

const TYPE_TO_PANEL={token:"tokens",line:"lines",zone:"zones",band:"geometry",gap:"geometry",phrase:"geometry",column:"geometry",indent:"geometry",separator:"geometry",fit:"geometry"};
export const panelForType=(type)=>TYPE_TO_PANEL[type]||null;
const PANEL_TYPES={tokens:["token"],lines:["line"],geometry:["band","gap","phrase","column","indent","separator","fit"],zones:["zone"]};
export const panelShowsType=(panel,type)=>PANEL_TYPES[panel]?.includes(type)||false;

function useAutoScroll(host,selection,panel){
  useEffect(()=>{
    if(!selection?.type||!host.current)return;
    const row=host.current.querySelector(`tr[data-type="${selection.type}"][data-id="${String(selection.id)}"]`);
    row?.scrollIntoView?.({block:"nearest",behavior:"smooth"});
  },[selection,panel]);
}

export default function Inspector({panel,layers,manifest,selection,onSelect}){
  const host=useRef(null);
  useAutoScroll(host,selection,panel);
  if(panel==="manifest")return <div ref={host}><pre>{JSON.stringify(manifest,null,2)}</pre></div>;
  if(panel==="raw")return <div ref={host}><pre>{JSON.stringify(layers,null,2)}</pre></div>;
  if(panel==="schema")return <div ref={host}><Schema schema={layers.schema}/></div>;
  if(panel==="geometry")return <div ref={host}><Geometry geometry={layers.geometry} selection={selection} onSelect={onSelect}/></div>;
  const configs={
    tokens:{data:layers.extract?.tokens||layers.paddle?.tokens,headers:["#","text","source","confidence","bbox"],type:"token",cells:(x,i)=>[i,x.text,x.source,x.confidence,x.bbox?.join(", ")]},
    lines:{data:layers.extract?.lines||layers.paddle?.lines,headers:["#","text","source","confidence","bbox"],type:"line",cells:(x,i)=>[x.line_id??i,x.text,x.source,x.confidence,x.bbox?.join(", ")]},
    zones:{data:layers.extract?.zones,headers:["zone","label","tokens","lines","bbox"],type:"zone",cells:(x)=>[x.zone_id,x.label,x.n_tokens,x.n_lines,x.bbox?.join(", ")]},
  };
  const config=configs[panel];if(!config?.data?.length)return <p className="muted">No {panel} artifact for this page.</p>;
  return <div ref={host}><table><thead><tr>{config.headers.map((h)=><th key={h}>{h}</th>)}</tr></thead><tbody>{config.data.map((item,i)=>{const id=config.cells(item,i)[0];return <tr key={`${id}-${i}`} data-type={config.type} data-id={id} className={selection?.type===config.type&&String(selection.id)===String(id)?"selected":""} onClick={()=>onSelect(config.type,id,item)}>{config.cells(item,i).map((value,j)=><td key={j}>{value??"—"}</td>)}</tr>})}</tbody></table></div>;
}

function Geometry({geometry,selection,onSelect}){
  if(!geometry)return <p className="muted">Stage 002.10 token-geometry artifact missing.</p>;
  const sections=[
    ["Baseline bands",geometry.baseline_bands,["#","baseline","confidence","slope","tokens","bbox"],"band",(x,i)=>[x.band_id??i,x.baseline_y,x.confidence,x.fit_slope,x.token_ids?.length,x.bbox?.join(", ")]],
    ["Gaps",geometry.gaps,["#","band","points","spaces","split","reason"],"gap",(x,i)=>[x.gap_id??i,x.band_id,x.gap_pt,x.estimated_spaces,String(x.split),x.reason]],
    ["Phrases",geometry.phrases,["#","band","observation","text","lexical","context"],"phrase",(x,i)=>[x.phrase_id??i,x.band_id,x.observation,x.text,x.money_lexical_confidence,x.amount_context_confidence]],
    ["Amount right-edge anchors",geometry.column_candidates,["#","right x","left envelope","drift","members","support","MAD","review"],"column",(x,i)=>[x.column_id??i,x.right_x,x.amount_left_x,x.drift_slope_dx_dy,x.n_phrases,x.support,x.right_mad,String(x.review)]],
    ["Label-indent anchors",geometry.label_indent_anchors,["#","left x","members","support","MAD","review"],"indent",(x,i)=>[x.indent_id??i,x.left_x,x.n_phrases,x.support,x.left_mad,String(x.review)]],
    ["Label/amount separator candidates",geometry.separator_candidates,["#","band","label","amount","x","gap","review"],"separator",(x,i)=>[x.separator_id??i,x.band_id,x.label_phrase_id,x.amount_phrase_id,x.x,x.gap_pt,String(x.review)]],
    ["Skew fits",geometry.fit_candidates,["#","column","slope","MAD","pairs","review"],"fit",(x,i)=>[x.fit_id??i,x.column_id,x.slope,x.slope_mad,x.n_pairs,String(x.review)]],
  ];
  return <><div className="card"><strong>{geometry.algorithm?.name}</strong> · v{geometry.algorithm?.version}<pre>{JSON.stringify(geometry.diagnostics,null,2)}</pre></div>{sections.map(([title,data,headers,type,cells])=><section className="geometry-section" key={title}><h3>{title}</h3>{data?.length?<table><thead><tr>{headers.map((h)=><th key={h}>{h}</th>)}</tr></thead><tbody>{data.map((item,i)=>{const id=cells(item,i)[0];return <tr key={id} data-type={type} data-id={id} className={selection?.type===type&&String(selection.id)===String(id)?"selected":""} onClick={()=>onSelect(type,id,item)}>{cells(item,i).map((value,j)=><td key={j}>{value??"—"}</td>)}</tr>})}</tbody></table>:<p className="muted">No candidates.</p>}</section>)}</>;
}

function Schema({schema}){if(!schema)return <p className="muted">Stage 005 schema artifact missing.</p>;return <><div className="card"><strong>{schema.schema_mode}</strong> · confidence {schema.confidence} · {schema.sequence?.contiguous?"contiguous":"sequence reset"}</div><table><thead><tr><th>zone</th><th>mode</th><th>roles</th><th>unit</th><th>confidence</th><th>QA</th><th>reasons</th></tr></thead><tbody>{schema.zone_schemas.map((x)=><tr key={x.zone_id}><td>{x.zone_id}</td><td>{x.schema_mode}</td><td>{x.col_roles.join(", ")}</td><td>{x.amount_unit}</td><td>{x.confidence}</td><td><span className={`flag flag-${x.qa_status}`}>{x.qa_status}</span></td><td>{x.reasons.join(", ")}</td></tr>)}</tbody></table></>}
