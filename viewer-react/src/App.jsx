import {useEffect, useRef, useState} from "react";
import {useViewer} from "./hooks/useViewer.js";
import PdfPane from "./components/PdfPane.jsx";
import Inspector,{PanelTabs,panelForType,panelShowsType} from "./components/Inspector.jsx";
import QaModal from "./components/QaModal.jsx";

const DEFAULT_OVERLAYS={
  tokens:true,lines:false,labels:true,
  bands:false,gaps:false,phrases:false,markers:false,money:false,columns:false,
  amountBands:false,labelIndents:false,separators:false,fits:false,
};

export default function App(){
  const v=useViewer();
  const [qaOpen,setQaOpen]=useState(new URLSearchParams(location.search).get("panel")==="qa");
  const [qaStage,setQaStage]=useState("schema"),[selection,setSelection]=useState(null),[split,setSplit]=useState(58);
  const [show,setShow]=useState(DEFAULT_OVERLAYS),[zoom,setZoom]=useState({mode:"fit",percent:100});
  const dragging=useRef(false),pages=v.viewer?.pages||[],at=pages.indexOf(v.page);
  const setPage=(page)=>{if(pages.includes(Number(page))){v.setPage(Number(page));setSelection(null)}};
  useEffect(()=>{const move=(e)=>{if(dragging.current)setSplit(Math.max(32,Math.min(76,e.clientX/innerWidth*100)))};const up=()=>{dragging.current=false;document.body.classList.remove("dragging")};addEventListener("pointermove",move);addEventListener("pointerup",up);return()=>{removeEventListener("pointermove",move);removeEventListener("pointerup",up)}},[]);
  useEffect(()=>{const key=(e)=>{if(e.key==="Escape")setQaOpen(false);if(e.target.matches("input,select"))return;if(e.key==="ArrowLeft"&&at>0)setPage(pages[at-1]);if(e.key==="ArrowRight"&&at>=0&&at<pages.length-1)setPage(pages[at+1])};addEventListener("keydown",key);return()=>removeEventListener("keydown",key)},[at,pages.join(",")]);
  const toggle=(key)=>(value)=>setShow((current)=>({...current,[key]:value}));
  const pickFromPdf=(type,id,item)=>{if(!panelShowsType(v.panel,type)){const target=panelForType(type);if(target)v.setPanel(target)}setSelection({type,id,item})};
  const pickFromTable=(type,id,item)=>setSelection({type,id,item});
  const selectedText=selection?`${selection.type} ${selection.id} · ${selection.item?.text||selection.item?.observation||selection.item?.label||""} · bbox [${selection.item?.bbox?.join(", ")||"—"}]`:"No selection";
  return <div className="app">
    <header>
      <div className="brand"><strong>OCR Viewer</strong><span>React + Vite</span></div>
      <Group label="Run"><select value={v.run} onChange={(e)=>v.setRun(e.target.value)}>{v.runs.map((run)=><option key={run}>{run}</option>)}</select><button title="Refresh runs" onClick={v.refreshRuns}>↻</button></Group>
      <Group label="Page"><button disabled={at<=0} onClick={()=>setPage(pages[at-1])}>←</button><select value={v.page} onChange={(e)=>setPage(e.target.value)}>{pages.map((p)=><option key={p}>{p}</option>)}</select><button disabled={at<0||at===pages.length-1} onClick={()=>setPage(pages[at+1])}>→</button><button title="Refresh current page artifacts" onClick={v.refreshPage}>↻</button></Group>
      <div className="group zoom"><button className={zoom.mode==="fit"?"active":""} onClick={()=>setZoom({mode:"fit",percent:100})}>Fit W</button><button className={zoom.mode==="height"?"active":""} onClick={()=>setZoom({mode:"height",percent:100})}>Fit H</button><button onClick={()=>setZoom({mode:"custom",percent:Math.max(25,zoom.percent-10)})}>−</button><input type="number" min="25" max="400" value={zoom.percent} onChange={(e)=>setZoom({mode:"custom",percent:Number(e.target.value)})}/><span>%</span><button onClick={()=>setZoom({mode:"custom",percent:Math.min(400,zoom.percent+10)})}>+</button></div>
      <div className="group overlays"><Check label="Tokens" checked={show.tokens} set={toggle("tokens")}/><Check label="OCR Lines" checked={show.lines} set={toggle("lines")}/></div>
      <details className="geometry-controls"><summary>Token Geometry</summary><div>
        <Check label="Bands" checked={show.bands} set={toggle("bands")}/><Check label="Gaps" checked={show.gaps} set={toggle("gaps")}/><Check label="Phrases" checked={show.phrases} set={toggle("phrases")}/><Check label="Markers" checked={show.markers} set={toggle("markers")}/><Check label="Money" checked={show.money} set={toggle("money")}/><Check label="Amount right anchors" checked={show.columns} set={toggle("columns")}/><Check label="Amount bands" checked={show.amountBands} set={toggle("amountBands")}/><Check label="Label indents" checked={show.labelIndents} set={toggle("labelIndents")}/><Check label="Separators" checked={show.separators} set={toggle("separators")}/><Check label="Alignment fits" checked={show.fits} set={toggle("fits")}/><Check label="Labels" checked={show.labels} set={toggle("labels")}/>
      </div></details>
      <Check label="Live" checked={v.liveUpdates} set={v.setLiveUpdates}/><button onClick={()=>setQaOpen(true)}>QA</button>
      <span className={`status ${v.error?"error":""}`} title={v.lastUpdated?`Artifacts updated ${v.lastUpdated.toLocaleTimeString()}`:""}>{v.error||(v.loading?"Loading…":`p.${v.page} · ${v.layers.extract?.tokens?.length??v.layers.paddle?.tokens?.length??0} tokens`)}</span>
    </header>
    <main style={{gridTemplateColumns:`minmax(360px,${split}%) 6px minmax(300px,1fr)`}}>
      <PdfPane viewer={v.viewer} page={v.page} layers={v.layers} overlays={show} zoom={zoom} selection={selection} onSelect={pickFromPdf}/>
      <div className="splitter" onPointerDown={()=>{dragging.current=true;document.body.classList.add("dragging")}}/>
      <aside><PanelTabs active={v.panel} onChange={v.setPanel}/><div className="panel"><Inspector panel={v.panel} layers={v.layers} manifest={v.manifest} selection={selection} onSelect={pickFromTable}/></div><QaModal open={qaOpen} onClose={()=>setQaOpen(false)} qa={v.qa} run={v.run} page={v.page} onPage={setPage} stage={qaStage} setStage={setQaStage}/></aside>
    </main>
    <footer>{selectedText}</footer>{v.loading&&<div className="loading"><span className="spinner"/>Loading…</div>}
  </div>;
}
function Group({label,children}){return <div className="group"><label>{label}</label>{children}</div>}
function Check({label,checked,set}){return <label className="check"><input type="checkbox" checked={checked} onChange={(e)=>set(e.target.checked)}/>{label}</label>}
