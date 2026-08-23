import * as pdfjsLib from "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/4.10.38/pdf.min.mjs";

pdfjsLib.GlobalWorkerOptions.workerSrc =
  "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/4.10.38/pdf.worker.min.mjs";

const $ = (selector) => document.querySelector(selector);
const state = {
  run: "extraction-smoke", page: 13, panel: "tokens",
  viewer: null, manifest: null, paddleQa: null, layoutQa: null, extractQa: null, cellsQa: null,
  paddle: null, layout: null, extract: null,
  pdf: null, viewport: null,
};

const esc = (value) => String(value ?? "").replace(/[&<>\"]/g, (char) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[char]));
const runBase = () => `../output/${encodeURIComponent(state.run)}`;
async function json(url) { const response = await fetch(url, {cache:"no-store"}); if (!response.ok) throw new Error(`${response.status} ${url}`); return response.json(); }
async function optionalJson(url) { if (!url) return null; try { return await json(url); } catch { return null; } }

function repoUrlFromPath(path) {
  const marker = "/NEP_PDF_DATA/";
  const index = String(path).indexOf(marker);
  return index >= 0 ? `../../${String(path).slice(index + marker.length)}` : path;
}

async function loadRun() {
  state.run = $("#run").value.trim();
  state.viewer = await json(`${runBase()}/viewer.json`);
  state.manifest = await json(`${runBase()}/manifest.json`);
  [state.paddleQa, state.layoutQa, state.extractQa, state.cellsQa] = await Promise.all([
    optionalJson(`${runBase()}/001.00-paddle-ocr/qa/summary.json`),
    optionalJson(`${runBase()}/002.00-layout/qa/summary.json`),
    optionalJson(`${runBase()}/004.00-extract/qa/summary.json`),
    optionalJson(`${runBase()}/003.00-table-cells/qa/summary.json`),
  ]);
  if (!state.viewer.pages.includes(state.page)) state.page = state.viewer.pages[0];
  $("#page").value = state.page;
  const pdfUrl = repoUrlFromPath(state.viewer.pdf);
  state.pdf = await pdfjsLib.getDocument(pdfUrl).promise;
  await loadPage();
}

async function loadPage() {
  state.page = Number($("#page").value);
  const padded = String(state.page).padStart(4,"0");
  [state.paddle, state.layout, state.extract] = await Promise.all([
    optionalJson(`${runBase()}/001.00-paddle-ocr/pages/page-${padded}.json`),
    optionalJson(`${runBase()}/002.00-layout/pages/page-${padded}.json`),
    optionalJson(`${runBase()}/004.00-extract/pages/page-${padded}.json`),
  ]);
  if (!state.paddle) throw new Error(`No Paddle layer for page ${state.page}`);
  const pdfPage = await state.pdf.getPage(state.page);
  const paneWidth = $("#document-pane").clientWidth - 28;
  const baseViewport = pdfPage.getViewport({scale: 1});
  const scale = Math.min(1.6, paneWidth / baseViewport.width);
  state.viewport = pdfPage.getViewport({scale});
  const canvas = $("#pdf-canvas");
  canvas.width = Math.ceil(state.viewport.width);
  canvas.height = Math.ceil(state.viewport.height);
  canvas.style.width = `${state.viewport.width}px`;
  canvas.style.height = `${state.viewport.height}px`;
  await pdfPage.render({canvasContext:canvas.getContext("2d"), viewport:state.viewport}).promise;
  drawOverlay(); renderPanel(); updateUrl();
  $("#status").textContent = `p.${state.page} · Paddle ${state.paddle?.tokens?.length ?? "missing"} tokens`;
}

function drawOverlay() {
  const svg = $("#overlay");
  const width = state.viewport.width, height = state.viewport.height;
  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
  svg.setAttribute("width", width); svg.setAttribute("height", height);
  const pageSize = state.paddle?.page_size_pt || [state.viewport.width / state.viewport.scale, state.viewport.height / state.viewport.scale];
  const sx = width / pageSize[0], sy = height / pageSize[1];
  const rects = [];
  const add = (layer, cls) => { for (const token of layer?.tokens || []) { const b=token.bbox; if (!b) continue; rects.push(`<rect class="${cls}" x="${b[0]*sx}" y="${b[1]*sy}" width="${Math.max(0,b[2]-b[0])*sx}" height="${Math.max(0,b[3]-b[1])*sy}"><title>${esc(token.text)}</title></rect>`); } };
  if ($("#show-paddle").checked) add(state.paddle,"box-paddle");
  if ($("#show-layout").checked) {
    for (const region of state.layout?.regions || []) {
      const b=region.bbox; if (!b) continue;
      const x=b[0]*sx, y=b[1]*sy, w=Math.max(0,b[2]-b[0])*sx, h=Math.max(0,b[3]-b[1])*sy;
      rects.push(`<rect class="box-layout" x="${x}" y="${y}" width="${w}" height="${h}"><title>${esc(region.label)} · ${esc(region.score)}</title></rect><text class="label-layout" x="${x+2}" y="${Math.max(9,y+10)}">${esc(region.region_id)} ${esc(region.label)}</text>`);
    }
  }
  if ($("#show-cells").checked) {
    for (const table of state.extract?.tables || []) for (const cell of table.cells || []) {
      const b=cell.bbox; if (!b) continue;
      rects.push(`<rect class="box-cell" x="${b[0]*sx}" y="${b[1]*sy}" width="${Math.max(0,b[2]-b[0])*sx}" height="${Math.max(0,b[3]-b[1])*sy}"><title>r${esc(cell.row)} c${esc(cell.col)} · ${esc(cell.text)}</title></rect>`);
    }
  }
  svg.innerHTML = rects.join("");
}

function renderPanel() {
  const host = $("#panel");
  if (state.panel === "tokens") {
    const rows = (state.paddle?.tokens||[]).map((t,i)=>`<tr><td>${i}</td><td>${esc(t.text)}</td><td>${esc(t.confidence)}</td><td>${esc(t.bbox?.join(", "))}</td></tr>`).join("");
    host.innerHTML=state.paddle ? `<table><thead><tr><th>#</th><th>Paddle token</th><th>confidence</th><th>bbox</th></tr></thead><tbody>${rows}</tbody></table>` : `<p class="muted">Paddle layer missing for this page.</p>`;
  } else if (state.panel === "lines") {
    const rows = (state.paddle?.lines||[]).map((line)=>`<tr><td>${line.line_id}</td><td>${esc(line.text)}</td><td>${esc(line.confidence)}</td><td>${esc(line.bbox?.join(", "))}</td></tr>`).join("");
    host.innerHTML=state.paddle ? `<table><thead><tr><th>#</th><th>Paddle line</th><th>confidence</th><th>bbox</th></tr></thead><tbody>${rows}</tbody></table>` : `<p class="muted">Paddle layer missing for this page.</p>`;
  } else if (state.panel === "regions") {
    const rows=(state.layout?.regions||[]).map((r)=>`<tr><td>${r.region_id}</td><td>${esc(r.label)}</td><td>${esc(r.score)}</td><td>${esc(r.chrome)}</td><td>${esc(r.bbox?.join(", "))}</td></tr>`).join("");
    host.innerHTML=state.layout ? `<table><thead><tr><th>#</th><th>label</th><th>score</th><th>chrome</th><th>bbox</th></tr></thead><tbody>${rows}</tbody></table>` : `<p class="muted">Layout layer missing for this page.</p>`;
  } else if (state.panel === "zones") {
    const rows=(state.extract?.zones||[]).map((z)=>`<tr><td>${z.zone_id}</td><td>${z.region_id}</td><td>${esc(z.label)}</td><td>${z.n_tokens}</td><td>${z.n_lines}</td><td>${esc(z.bbox?.join(", "))}</td></tr>`).join("");
    host.innerHTML=state.extract ? `<table><thead><tr><th>zone</th><th>region</th><th>label</th><th>tokens</th><th>lines</th><th>bbox</th></tr></thead><tbody>${rows}</tbody></table>` : `<p class="muted">Canonical extract missing for this page.</p>`;
  } else if (state.panel === "cells") {
    const cells=(state.extract?.tables||[]).flatMap((table)=>(table.cells||[]).map((cell)=>({...cell,table_id:table.table_id})));
    const rows=cells.map((c)=>`<tr><td>${c.table_id}</td><td>${c.row}</td><td>${c.col}</td><td>${esc(c.text)}</td><td>${esc(c.score)}</td><td>${esc(c.bbox?.join(", "))}</td></tr>`).join("");
    host.innerHTML=cells.length ? `<table><thead><tr><th>table</th><th>row</th><th>col</th><th>text</th><th>score</th><th>bbox</th></tr></thead><tbody>${rows}</tbody></table>` : `<p class="muted">No selective cell layer assembled for this page.</p>`;
  } else if (state.panel === "qa") {
    host.innerHTML=`<div class="card"><h3>Canonical extract</h3><pre>${esc(JSON.stringify(state.extractQa,null,2))}</pre></div><div class="card"><h3>Selective cells</h3><pre>${esc(JSON.stringify(state.cellsQa,null,2))}</pre></div><div class="card"><h3>Paddle OCR (canonical)</h3><pre>${esc(JSON.stringify(state.paddleQa,null,2))}</pre></div><div class="card"><h3>Layout regions</h3><pre>${esc(JSON.stringify(state.layoutQa,null,2))}</pre></div>`;
  } else if (state.panel === "manifest") host.innerHTML=`<pre>${esc(JSON.stringify(state.manifest,null,2))}</pre>`;
  else host.innerHTML=`<pre>${esc(JSON.stringify({extract:state.extract,paddle:state.paddle,layout:state.layout},null,2))}</pre>`;
}

function step(delta) { const pages=state.viewer.pages, at=pages.indexOf(state.page), next=pages[at+delta]; if(next){$("#page").value=next; loadPage();} }
function updateUrl(){const url=new URL(location.href);url.searchParams.set("run",state.run);url.searchParams.set("page",state.page);url.searchParams.set("panel",state.panel);history.replaceState(null,"",url);}

$("#load-run").onclick=loadRun; $("#page").onchange=loadPage; $("#prev").onclick=()=>step(-1); $("#next").onclick=()=>step(1);
$("#show-paddle").onchange=drawOverlay; $("#show-layout").onchange=drawOverlay; $("#show-cells").onchange=drawOverlay;
document.querySelectorAll("nav button").forEach((button)=>button.onclick=()=>{document.querySelectorAll("nav button").forEach((b)=>b.classList.remove("active"));button.classList.add("active");state.panel=button.dataset.panel;renderPanel();updateUrl();});
const query=new URL(location.href).searchParams; state.run=query.get("run")||state.run; state.page=Number(query.get("page")||state.page); state.panel=query.get("panel")||state.panel; $("#run").value=state.run; $("#page").value=state.page;
document.querySelectorAll("nav button").forEach((b)=>b.classList.toggle("active",b.dataset.panel===state.panel));
loadRun().catch((error)=>{$("#status").textContent=error.message;console.error(error);});
