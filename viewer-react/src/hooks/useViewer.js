import {useCallback, useEffect, useMemo, useState} from "react";
import {json, listRuns, pagePath, runPath} from "../lib/api.js";

const STAGES = {
  paddle:"001.00-paddle-ocr", geometry:"002.10-token-geometry",
  extract:"004.00-extract", schema:"005.00-schema",
};

function initialQuery() {
  const query = new URLSearchParams(location.search);
  const requestedPanel=query.get("panel"),panels=new Set(["tokens","lines","geometry","zones","schema","manifest","raw"]);
  return {run:query.get("run") || "NEP-2027-VOLUME-2B_OCR", page:Number(query.get("page") || 13), panel:panels.has(requestedPanel)?requestedPanel:"tokens"};
}

export function useViewer() {
  const initial = useMemo(initialQuery, []);
  const [runs,setRuns]=useState([]), [run,setRun]=useState(initial.run), [page,setPage]=useState(initial.page), [panel,setPanel]=useState(initial.panel);
  const [viewer,setViewer]=useState(null), [manifest,setManifest]=useState(null), [qa,setQa]=useState({}), [layers,setLayers]=useState({});
  const [loading,setLoading]=useState(true), [error,setError]=useState("");
  const [liveUpdates,setLiveUpdates]=useState(false), [revision,setRevision]=useState(0), [lastUpdated,setLastUpdated]=useState(null);

  const refreshRuns = useCallback(async()=>{const found=await listRuns();setRuns(found);if(found.length&&!found.includes(run))setRun(found.includes("NEP-2027-VOLUME-2B_OCR")?"NEP-2027-VOLUME-2B_OCR":found.at(-1));},[run]);
  useEffect(()=>{refreshRuns().catch((e)=>setError(e.message));},[]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(()=>{if(!run)return;let live=true;(async()=>{setLoading(true);setError("");try{
    const [nextViewer,nextManifest,paddle,geometry,extract,schema,execution]=await Promise.all([
      json(runPath(run,"viewer.json")),json(runPath(run,"manifest.json")),
      json(runPath(run,`${STAGES.paddle}/qa/summary.json`),true),
      json(runPath(run,`${STAGES.geometry}/qa/summary.json`),true),
      json(runPath(run,`${STAGES.extract}/qa/summary.json`),true),
      json(runPath(run,`${STAGES.schema}/qa/summary.json`),true),json(runPath(run,"999.00-run-qa/execution.json"),true),
    ]); if(!live)return;setViewer(nextViewer);setManifest(nextManifest);setQa({paddle,geometry,extract,schema,run:execution});
    setPage((current)=>nextViewer.pages.includes(current)?current:nextViewer.pages[0]);
  }catch(e){if(live)setError(e.message);}finally{if(live)setLoading(false);}})();return()=>{live=false};},[run]);

  useEffect(()=>{if(!run||!viewer||!page)return;let live=true;setLayers({});(async()=>{try{
    const [paddle,geometry,extract,schema]=await Promise.all([
      json(pagePath(run,STAGES.paddle,page),true),
      json(pagePath(run,STAGES.geometry,page),true),
      json(pagePath(run,STAGES.extract,page),true),json(pagePath(run,STAGES.schema,page),true),
    ]);if(live){setLayers({paddle,geometry,extract,schema});setLastUpdated(new Date());}
  }catch(e){if(live)setError(e.message);}})();return()=>{live=false};},[run,page,viewer,revision]);

  useEffect(()=>{if(!liveUpdates)return;const timer=setInterval(()=>setRevision((value)=>value+1),3000);return()=>clearInterval(timer);},[liveUpdates]);

  useEffect(()=>{if(!run||!page)return;const url=new URL(location.href);url.searchParams.set("run",run);url.searchParams.set("page",page);url.searchParams.set("panel",panel);history.replaceState(null,"",url);},[run,page,panel]);
  return {runs,run,setRun,page,setPage,panel,setPanel,viewer,manifest,qa,layers,loading,error,refreshRuns,liveUpdates,setLiveUpdates,lastUpdated,refreshPage:()=>setRevision((value)=>value+1)};
}

export {STAGES};
