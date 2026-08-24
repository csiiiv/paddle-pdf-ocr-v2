export const TOGGLE_KEYS=["tokens","lines","labels","bands","gaps","phrases","markers","money","columns","amountBands","labelIndents","separators","fits","headerSections","columnSections","rowSections","cellSections","rowBoundaries","reviewedReferences"];
export const DEFAULT_OVERLAYS={
  tokens:true,lines:false,labels:true,
  bands:false,gaps:false,phrases:false,markers:false,money:false,columns:false,
  amountBands:false,labelIndents:false,separators:false,fits:false,
  headerSections:true,columnSections:true,rowSections:false,cellSections:false,rowBoundaries:true,reviewedReferences:false,
};
export const DEFAULT_ZOOM={mode:"fit",percent:100};
export const DEFAULT_SPLIT=58;
export const DEFAULT_FLAG_FILTER={includeOn:false,include:"",excludeOn:false,exclude:""};

const CUSTOM_ZOOM="custom,";
const bounded=(value,min,max,fallback)=>{
  if(value===null||value===undefined||value==="")return fallback;
  const n=Number(value);
  return Number.isFinite(n)?Math.min(max,Math.max(min,n)):fallback;
};
const flagOn=(value)=>value==="1"||value==="true"||value==="on";

/** Expand comma-separated pages and inclusive ranges (`1-3,5` → {1,2,3,5}). Invalid tokens are skipped. */
export function parsePageRanges(spec){
  const pages=new Set();
  if(!spec?.trim())return pages;
  for(const raw of spec.split(",")){
    const part=raw.trim();
    if(!part)continue;
    if(part.includes("-")){
      const [left,right]=part.split("-",2);
      const start=Number(left),end=Number(right);
      if(!Number.isInteger(start)||!Number.isInteger(end)||start<1||end<start)continue;
      for(let page=start;page<=end;page+=1)pages.add(page);
    }else{
      const page=Number(part);
      if(Number.isInteger(page)&&page>=1)pages.add(page);
    }
  }
  return pages;
}

/** When include is on, page must be in that set (empty set ⇒ none). When exclude is on, page must not be in that set. */
export function pagePassesFlagFilter(page,filter=DEFAULT_FLAG_FILTER){
  const n=Number(page);
  if(!Number.isInteger(n)||n<1)return false;
  if(filter.includeOn){
    const include=parsePageRanges(filter.include);
    if(!include.has(n))return false;
  }
  if(filter.excludeOn&&parsePageRanges(filter.exclude).has(n))return false;
  return true;
}

export function parseView(params){
  const overlays={...DEFAULT_OVERLAYS};
  const listed=params.get("overlays");
  if(listed!==null){
    const enabled=new Set(listed.split(",").map((key)=>key.trim()).filter(Boolean));
    for(const key of TOGGLE_KEYS)overlays[key]=enabled.has(key);
  }
  const zoomParam=params.get("zoom");
  let zoom=DEFAULT_ZOOM;
  if(zoomParam==="fit"||zoomParam==="height")zoom={mode:zoomParam,percent:100};
  else if(zoomParam?.startsWith(CUSTOM_ZOOM))zoom={mode:"custom",percent:bounded(zoomParam.slice(CUSTOM_ZOOM.length),25,400,100)};
  const flagFilter={
    includeOn:flagOn(params.get("flagIncludeOn")),
    include:params.get("flagInclude")??"",
    excludeOn:flagOn(params.get("flagExcludeOn")),
    exclude:params.get("flagExclude")??"",
  };
  return {overlays,zoom,split:bounded(params.get("split"),32,76,DEFAULT_SPLIT),flagFilter};
}

export function writeView(params,{overlays,zoom,split,flagFilter=DEFAULT_FLAG_FILTER}){
  const on=TOGGLE_KEYS.filter((key)=>overlays[key]).join(",");
  const defaultOn=TOGGLE_KEYS.filter((key)=>DEFAULT_OVERLAYS[key]).join(",");
  if(on===defaultOn)params.delete("overlays");else params.set("overlays",on);
  const zoomValue=zoom.mode==="custom"?`${CUSTOM_ZOOM}${zoom.percent}`:zoom.mode;
  if(zoomValue===DEFAULT_ZOOM.mode)params.delete("zoom");else params.set("zoom",zoomValue);
  if(split===DEFAULT_SPLIT)params.delete("split");else params.set("split",split);
  if(flagFilter.include)params.set("flagInclude",flagFilter.include);else params.delete("flagInclude");
  if(flagFilter.includeOn)params.set("flagIncludeOn","1");else params.delete("flagIncludeOn");
  if(flagFilter.exclude)params.set("flagExclude",flagFilter.exclude);else params.delete("flagExclude");
  if(flagFilter.excludeOn)params.set("flagExcludeOn","1");else params.delete("flagExcludeOn");
  return params;
}
