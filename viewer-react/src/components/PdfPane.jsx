import {useEffect,useMemo,useRef,useState} from "react";
import * as pdfjs from "pdfjs-dist/legacy/build/pdf.mjs";
import PdfWorker from "pdfjs-dist/legacy/build/pdf.worker.min.mjs?worker";
import {pdfUrls} from "../lib/api.js";

pdfjs.GlobalWorkerOptions.workerPort=new PdfWorker();

export default function PdfPane({viewer,page,layers,overlays,zoom,selection,onSelect}){
  const host=useRef(null),canvas=useRef(null),[pdf,setPdf]=useState(null),[pdfPage,setPdfPage]=useState(null),[viewport,setViewport]=useState(null),[error,setError]=useState(""),[size,setSize]=useState({width:700,height:800});
  useEffect(()=>{if(!host.current)return;const observer=new ResizeObserver(([entry])=>setSize({width:entry.contentRect.width,height:entry.contentRect.height}));observer.observe(host.current);return()=>observer.disconnect()},[]);
  useEffect(()=>{if(!viewer?.pdf)return;let live=true,task;setError("");(async()=>{const failures=[];for(const url of pdfUrls(viewer.pdf)){try{task=pdfjs.getDocument({url,isEvalSupported:false,disableStream:true,disableAutoFetch:true,rangeChunkSize:65536});const doc=await task.promise;if(live){setPdf(doc);return}}catch(reason){failures.push(`${url}: ${reason?.message||reason}`)}}if(live)setError(`PDF failed to load. ${failures.join(" | ")}`)})();return()=>{live=false;task?.destroy()}},[viewer?.pdf]);
  useEffect(()=>{if(!pdf||!page)return;let live=true;pdf.getPage(page).then((value)=>{if(live)setPdfPage(value)});return()=>{live=false}},[pdf,page]);
  useEffect(()=>{if(!pdfPage||!canvas.current)return;const base=pdfPage.getViewport({scale:1}),fitW=Math.max(.25,(size.width-28)/base.width),fitH=Math.max(.25,(size.height-28)/base.height),scale=zoom.mode==="height"?fitH:fitW*(zoom.mode==="custom"?zoom.percent/100:1),vp=pdfPage.getViewport({scale:Math.min(5,scale)});setViewport(vp);const el=canvas.current;el.width=Math.ceil(vp.width);el.height=Math.ceil(vp.height);el.style.width=`${vp.width}px`;el.style.height=`${vp.height}px`;const task=pdfPage.render({canvasContext:el.getContext("2d"),viewport:vp});return()=>task.cancel()},[pdfPage,size,zoom]);
  const marks=useMemo(()=>buildMarks(layers,overlays,viewport,selection),[layers,overlays,viewport,selection]);
  return <section className="pdf-pane" ref={host} aria-label="PDF page">{error&&<div className="pdf-error">{error}</div>}<div className="page-stage"><canvas ref={canvas}/>{viewport&&<svg className="overlay" width={viewport.width} height={viewport.height} viewBox={`0 0 ${viewport.width} ${viewport.height}`}>{marks.map((mark)=><g key={mark.key}>{mark.line?<line {...mark.line} className={`${mark.cls}${mark.selected?" selected-box":""}`} onClick={()=>onSelect(mark.type,mark.id,mark.item)}/>:<rect {...mark.rect} className={`${mark.cls}${mark.selected?" selected-box":""}`} onClick={()=>onSelect(mark.type,mark.id,mark.item)}/>}<title>{mark.title}</title>{mark.label&&<text x={mark.label.x} y={mark.label.y}>{mark.label.text}</text>}</g>)}</svg>}</div></section>;
}

function buildMarks(layers,show,viewport,selection){
  if(!viewport)return[];
  const source=layers.extract||layers.paddle,size=source?.page_size_pt||[viewport.width/viewport.scale,viewport.height/viewport.scale],sx=viewport.width/size[0],sy=viewport.height/size[1],out=[];
  const selected=(type,id)=>selection?.type===type&&String(selection.id)===String(id);
  const addBox=(item,type,id,cls,title,label)=>{const b=item.bbox;if(!b)return;const rect={x:b[0]*sx,y:b[1]*sy,width:Math.max(.6,(b[2]-b[0])*sx),height:Math.max(.6,(b[3]-b[1])*sy)};out.push({key:`${type}-${id}`,type,id,item,cls,title,rect,selected:selected(type,id),label:show.labels&&label?{x:rect.x+2,y:Math.max(10,rect.y+10),text:label}:null})};
  const addLine=(item,type,id,cls,segment,title,label,keyId)=>{if(!segment)return;const line={x1:segment[0]*sx,y1:segment[1]*sy,x2:segment[2]*sx,y2:segment[3]*sy};out.push({key:`${type}-${keyId??id}`,type,id,item,cls,title,line,selected:selected(type,id),label:show.labels&&label?{x:line.x1+2,y:Math.max(10,line.y1-2),text:label}:null})};
  if(show.tokens)(source?.tokens||[]).forEach((item,i)=>addBox(item,"token",i,"box-token",item.text));
  if(show.lines)(source?.lines||[]).forEach((item,i)=>addBox(item,"line",item.line_id??i,"box-line",item.text));
  const geometry=layers.geometry;
  if(show.bands)(geometry?.baseline_bands||[]).forEach((item,i)=>addLine(item,"band",item.band_id??i,"guide-band",item.baseline_segment,`band ${item.band_id} · confidence ${item.confidence}`,`B${item.band_id} ${item.confidence}`));
  if(show.gaps)(geometry?.gaps||[]).forEach((item,i)=>addBox(item,"gap",item.gap_id??i,item.split?"box-gap-split":"box-gap",`${item.gap_pt}pt · ${item.estimated_spaces} spaces · ${item.reason||"no split"}`,`G${item.gap_id} ${item.estimated_spaces}s`));
  if(show.phrases)(geometry?.phrases||[]).forEach((item,i)=>addBox(item,"phrase",item.phrase_id??i,"box-phrase",`${item.observation} · ${item.text}`,`P${item.phrase_id}`));
  if(show.markers)(geometry?.phrases||[]).filter((x)=>x.observation==="marker_candidate").forEach((item,i)=>addBox(item,"phrase",item.phrase_id??i,"box-marker",item.text,`M${item.phrase_id}`));
  if(show.money)(geometry?.phrases||[]).filter((x)=>x.observation==="money_candidate").forEach((item,i)=>addBox(item,"phrase",item.phrase_id??i,"box-money",`${item.text} · lexical ${item.money_lexical_confidence} · context ${item.amount_context_confidence}`,`$${item.phrase_id}`));
  if(show.columns)(geometry?.column_candidates||[]).forEach((item,i)=>addLine(item,"column",item.column_id??i,item.recurring?"guide-column":"guide-column-review",item.line_segment||[item.right_x,0,item.right_x,size[1]],`right@${item.right_x_reference_y??"page"} ${item.right_x} · drift ${item.drift_slope_dx_dy??0} · n=${item.n_phrases} · ${item.support||"legacy"}`,`C${item.column_id} n${item.n_phrases}`));
  if(show.amountBands)(geometry?.column_candidates||[]).forEach((item,i)=>[item.left_line_segment,item.line_segment].forEach((segment,edge)=>addLine(item,"column",item.column_id??i,"guide-amount-band",segment,`amount band ${edge?"right":"left"} · n=${item.n_phrases}`,`A${item.column_id}`,`${item.column_id}:${edge}`)));
  if(show.labelIndents)(geometry?.label_indent_anchors||[]).forEach((item,i)=>addLine(item,"indent",item.indent_id??i,item.review?"guide-indent-review":"guide-indent",item.line_segment,`${item.support} · x ${item.left_x} · n=${item.n_phrases}`,`I${item.indent_id} n${item.n_phrases}`));
  if(show.separators)(geometry?.separator_candidates||[]).forEach((item,i)=>addLine(item,"separator",item.separator_id??i,"guide-separator",item.line_segment,`label/amount gap ${item.gap_pt}pt · review candidate`,`S${item.separator_id}`));
  if(show.fits)(geometry?.fit_candidates||[]).forEach((fit)=>(fit.segments||[]).forEach((segment,i)=>addLine(fit,"fit",fit.fit_id,fit.review?"guide-fit-review":"guide-fit",segment,`slope ${fit.slope} · MAD ${fit.slope_mad}`,`F${fit.fit_id}`,`${fit.fit_id}:${i}`)));
  return out;
}
