import {describe, expect, it} from "vitest";
import {
  DEFAULT_FLAG_FILTER,
  DEFAULT_OVERLAYS,
  pagePassesFlagFilter,
  parsePageRanges,
  parseView,
  writeView,
} from "./viewState.js";

const view=(overlays={},zoom={mode:"fit",percent:100},split=58,flagFilter=DEFAULT_FLAG_FILTER)=>({
  overlays:{...DEFAULT_OVERLAYS,...overlays},zoom,split,flagFilter:{...DEFAULT_FLAG_FILTER,...flagFilter},
});

describe("viewState",()=>{
  it("falls back to defaults when params are absent",()=>{
    expect(parseView(new URLSearchParams(""))).toEqual(view());
  });

  it("round-trips toggles, zoom, and split through the URL",()=>{
    const state=view({tokens:false,labels:true,columns:true,separators:true},{mode:"custom",percent:175},64);
    const params=writeView(new URLSearchParams(""),state);
    expect(params.get("overlays")).toBe("labels,columns,separators,headerSections,columnSections,rowBoundaries");
    expect(params.get("zoom")).toBe("custom,175");
    expect(params.get("split")).toBe("64");
    expect(parseView(params)).toEqual(state);
  });

  it("strips params that match defaults",()=>{
    expect([...writeView(new URLSearchParams("overlays=tokens&zoom=fit&split=58"),view())].map(([key])=>key)).toEqual([]);
  });

  it("clamps out-of-range zoom and split values",()=>{
    const parsed=parseView(new URLSearchParams("zoom=custom,900&split=200"));
    expect(parsed.zoom).toEqual({mode:"custom",percent:400});
    expect(parsed.split).toBe(76);
  });

  it("ignores unknown toggle keys",()=>{
    expect(parseView(new URLSearchParams("overlays=tokens,hack"))).toEqual(view({tokens:true,labels:false,headerSections:false,columnSections:false,rowBoundaries:false}));
  });

  it("round-trips flag include/exclude filters through the URL",()=>{
    const state=view({},undefined,undefined,{includeOn:true,include:"13-20,106",excludeOn:true,exclude:"15"});
    const params=writeView(new URLSearchParams(""),state);
    expect(params.get("flagInclude")).toBe("13-20,106");
    expect(params.get("flagIncludeOn")).toBe("1");
    expect(params.get("flagExclude")).toBe("15");
    expect(params.get("flagExcludeOn")).toBe("1");
    expect(parseView(params)).toEqual(state);
  });
});

describe("parsePageRanges",()=>{
  it("expands comma-separated pages and inclusive ranges",()=>{
    expect([...parsePageRanges("1-2,3,5-7")].sort((a,b)=>a-b)).toEqual([1,2,3,5,6,7]);
  });

  it("skips blank and invalid tokens while typing",()=>{
    expect([...parsePageRanges("13-20,")]).toEqual([13,14,15,16,17,18,19,20]);
    expect([...parsePageRanges("1-")]).toEqual([]);
    expect([...parsePageRanges("abc,8")]).toEqual([8]);
  });
});

describe("pagePassesFlagFilter",()=>{
  it("passes all pages when filters are off",()=>{
    expect(pagePassesFlagFilter(15)).toBe(true);
  });

  it("requires membership when include is on",()=>{
    expect(pagePassesFlagFilter(15,{...DEFAULT_FLAG_FILTER,includeOn:true,include:"13-20"})).toBe(true);
    expect(pagePassesFlagFilter(21,{...DEFAULT_FLAG_FILTER,includeOn:true,include:"13-20"})).toBe(false);
    expect(pagePassesFlagFilter(15,{...DEFAULT_FLAG_FILTER,includeOn:true,include:""})).toBe(false);
  });

  it("drops excluded pages and combines with include",()=>{
    expect(pagePassesFlagFilter(15,{...DEFAULT_FLAG_FILTER,excludeOn:true,exclude:"15,18"})).toBe(false);
    expect(pagePassesFlagFilter(16,{...DEFAULT_FLAG_FILTER,includeOn:true,include:"13-20",excludeOn:true,exclude:"15"})).toBe(true);
    expect(pagePassesFlagFilter(15,{...DEFAULT_FLAG_FILTER,includeOn:true,include:"13-20",excludeOn:true,exclude:"15"})).toBe(false);
  });
});
