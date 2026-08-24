import {useCallback, useEffect, useMemo, useState} from "react";
import {flagIndex, json, listRuns, pagePath, runPath} from "../lib/api.js";

const STAGES = {
  paddle:"001.00-paddle-ocr", geometry:"002.11-token-geometry-repair",
  sections:"002.20-table-structure", tree:"002.30-by-ou-tree",
  pap:"002.40-pap-tree",
  totals:"002.50-tree-totals",
};

function initialQuery() {
  const query = new URLSearchParams(location.search);
  const requestedPanel=query.get("panel"),panels=new Set(["tokens","lines","geometry","flags","sections","tree","pap","manifest","raw"]);
  return {run:query.get("run") || "NEP-2027-VOLUME-2B_OCR", page:Number(query.get("page") || 13), panel:panels.has(requestedPanel)?requestedPanel:"tokens"};
}

function clearRunScoped(setters) {
  setters.setViewer(null);
  setters.setManifest(null);
  setters.setTree(null);
  setters.setPapTree(null);
  setters.setLayers({});
  setters.setAllLayers([]);
  setters.setQa({});
  setters.setFlagPages([]);
  setters.setError("");
}

export function useViewer() {
  const initial = useMemo(initialQuery, []);
  const [runs,setRuns]=useState([]), [run,setRunState]=useState(initial.run), [page,setPage]=useState(initial.page), [panel,setPanel]=useState(initial.panel);
  const [viewer,setViewer]=useState(null), [manifest,setManifest]=useState(null), [seeds,setSeeds]=useState(null), [tree,setTree]=useState(null), [papTree,setPapTree]=useState(null), [qa,setQa]=useState({}), [layers,setLayers]=useState({});
  const [flagPages,setFlagPages]=useState([]);
  const [loading,setLoading]=useState(true), [error,setError]=useState("");
  const [liveUpdates,setLiveUpdates]=useState(false), [revision,setRevision]=useState(0), [lastUpdated,setLastUpdated]=useState(null);
  const [allPageData,setAllPageData]=useState(false),[allLayers,setAllLayers]=useState([]),[allLoading,setAllLoading]=useState(false);

  const runScopedSetters = useMemo(()=>({
    setViewer,setManifest,setTree,setPapTree,setLayers,setAllLayers,setQa,setFlagPages,setError,
  }),[]);

  const setRun = useCallback((nextRun)=>{
    const name=String(nextRun||"");
    if(!name||name===run)return;
    clearRunScoped(runScopedSetters);
    setLoading(true);
    setRunState(name);
  },[run,runScopedSetters]);

  const refreshRuns = useCallback(async()=>{
    const found=await listRuns();
    setRuns(found);
    if(found.length&&!found.includes(run)){
      const fallback=found.includes("NEP-2027-VOLUME-2B_OCR")?"NEP-2027-VOLUME-2B_OCR":found.at(-1);
      clearRunScoped(runScopedSetters);
      setLoading(true);
      setRunState(fallback);
    }
  },[run,runScopedSetters]);
  useEffect(()=>{refreshRuns().catch((e)=>setError(e.message));},[]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(()=>{if(!run)return;let live=true;(async()=>{setLoading(true);setError("");try{
    const [nextViewer,nextManifest,nextSeeds,nextTree,nextPapTree,paddle,geometry,sections,treeQa,papQa,totalsQa,execution,flags]=await Promise.all([
      json(runPath(run,"viewer.json")),
      json(runPath(run,"manifest.json"),true),
      json("fixtures/by_ou_table_seeds.json",true),
      json(runPath(run,`${STAGES.tree}/tree.json`),true),
      json(runPath(run,`${STAGES.pap}/tree.json`),true),
      json(runPath(run,`${STAGES.paddle}/qa/summary.json`),true),
      json(runPath(run,`${STAGES.geometry}/qa/summary.json`),true),
      json(runPath(run,`${STAGES.sections}/qa/summary.json`),true),
      json(runPath(run,`${STAGES.tree}/qa/summary.json`),true),
      json(runPath(run,`${STAGES.pap}/qa/summary.json`),true),
      json(runPath(run,`${STAGES.totals}/qa/summary.json`),true),
      json(runPath(run,"999.00-run-qa/execution.json"),true),
      flagIndex(run),
    ]); if(!live)return;
    if(!nextViewer?.pages?.length)throw new Error(`Run ${run} has no pages in viewer.json`);
    setViewer(nextViewer);setManifest(nextManifest);setSeeds(nextSeeds);setTree(nextTree);setPapTree(nextPapTree);setQa({paddle,geometry,sections,tree:treeQa,pap:papQa,totals:totalsQa,run:execution});
    const fromIndex=(flags?.pages||[]).map((item)=>({page:Number(item.page),n:Number(item.n_flags??item.n??0)})).filter((item)=>item.n>0);
    const fromQa=(sections?.pages||[]).map((item)=>({page:Number(item.page),n:Number(item.n_flags??item.n_findings??0)})).filter((item)=>item.n>0);
    const indexFlags=fromIndex.reduce((total,item)=>total+item.n,0);
    const qaFlags=fromQa.reduce((total,item)=>total+item.n,0);
    // Prefer the broader index: a partial QA re-run can shrink summary.json while page artifacts remain complete.
    setFlagPages(indexFlags>=qaFlags&&fromIndex.length?fromIndex:fromQa);
    setPage((current)=>nextViewer.pages.includes(current)?current:nextViewer.pages[0]);
  }catch(e){if(live){clearRunScoped(runScopedSetters);setError(e.message);}}finally{if(live)setLoading(false);}})();return()=>{live=false};},[run,revision,runScopedSetters]);

  useEffect(()=>{if(!run||!viewer||!page)return;let live=true;setLayers({});(async()=>{try{
    const [paddle,geometry,sections,sectionsQa]=await Promise.all([
      json(pagePath(run,STAGES.paddle,page),true),
      json(pagePath(run,STAGES.geometry,page),true),
      json(pagePath(run,STAGES.sections,page),true),
      json(runPath(run,`${STAGES.sections}/qa/summary.json`),true),
    ]);if(live){setLayers({paddle,geometry,sections,reviewedTable:reviewedTableForPage(seeds,page)});if(sectionsQa)setQa((current)=>({...current,sections:sectionsQa}));setLastUpdated(new Date());}
  }catch(e){if(live)setError(e.message);}})();return()=>{live=false};},[run,page,viewer,seeds,revision]);

  useEffect(()=>{const needsAll=allPageData||panel==="flags";if(!needsAll||!run||!viewer){setAllLayers([]);return;}const stage=panel==="tokens"||panel==="lines"?"paddle":panel==="geometry"?"geometry":panel==="sections"||panel==="flags"?"sections":null;if(!stage){setAllLayers([]);return;}const flagged=new Set(flagPages.map((item)=>Number(item.page))),targetPages=panel==="flags"&&flagged.size?viewer.pages.filter((pageNumber)=>flagged.has(Number(pageNumber))):viewer.pages;let live=true;setAllLoading(true);(async()=>{try{const artifacts=await Promise.all(targetPages.map(async(pageNumber)=>({page:pageNumber,[stage]:await json(pagePath(run,STAGES[stage],pageNumber),true),reviewedTable:reviewedTableForPage(seeds,pageNumber)})));if(live)setAllLayers(artifacts.filter((item)=>item[stage]||item.reviewedTable));}catch(e){if(live)setError(e.message);}finally{if(live)setAllLoading(false);}})();return()=>{live=false};},[allPageData,run,viewer,panel,seeds,revision,flagPages]);

  useEffect(()=>{if(!liveUpdates)return;const timer=setInterval(()=>setRevision((value)=>value+1),3000);return()=>clearInterval(timer);},[liveUpdates]);

  useEffect(()=>{if(!run||!page)return;const url=new URL(location.href);url.searchParams.set("run",run);url.searchParams.set("page",page);url.searchParams.set("panel",panel);history.replaceState(null,"",url);},[run,page,panel]);
  return {runs,run,setRun,page,setPage,panel,setPanel,viewer,manifest,tree,papTree,qa,layers,flagPages,loading,error,refreshRuns,liveUpdates,setLiveUpdates,lastUpdated,refreshPage:()=>setRevision((value)=>value+1),allPageData,setAllPageData,allLayers,allLoading};
}

function reviewedTableForPage(seeds,page){
  return seeds?.tables?.find((table)=>page>=table.start.page&&page<=table.end.page)||null;
}

export {STAGES};
