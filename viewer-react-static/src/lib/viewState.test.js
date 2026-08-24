import {describe, expect, it} from "vitest";
import {parseView, writeView} from "./viewState.js";

const params = (query) => new URLSearchParams(query);

describe("parseView", () => {
  it("returns defaults for an empty query", () => {
    const view = parseView(params(""));
    expect(view.doc).toBe("");
    expect(view.tree).toBe("");
    expect(view.page).toBeNull();
    expect(view.zoom).toEqual({mode:"fit", percent:100});
    expect(view.split).toBe(58);
    expect(view.overlay).toBe("hide");
    expect(view.pane).toBe("data");
  });

  it("reads doc, tree, page, node, custom zoom, overlay, and pane", () => {
    const view = parseView(params("doc=NEP-2027-VOLUME-2B&tree=pap&page=115&node=r1&zoom=custom,150&split=66&overlay=off&pane=pdf"));
    expect(view.doc).toBe("NEP-2027-VOLUME-2B");
    expect(view.tree).toBe("pap");
    expect(view.page).toBe(115);
    expect(view.node).toBe("r1");
    expect(view.zoom).toEqual({mode:"custom", percent:150});
    expect(view.split).toBe(66);
    expect(view.overlay).toBe("off");
    expect(view.pane).toBe("pdf");
  });

  it("falls back to hide for unknown overlay modes", () => {
    expect(parseView(params("overlay=bogus")).overlay).toBe("hide");
  });

  it("falls back to data for unknown pane modes", () => {
    expect(parseView(params("pane=bogus")).pane).toBe("data");
  });

  it("bounds custom zoom and split", () => {
    expect(parseView(params("zoom=custom,999")).zoom.percent).toBe(400);
    expect(parseView(params("zoom=custom,1")).zoom.percent).toBe(25);
    expect(parseView(params("split=99")).split).toBe(76);
    expect(parseView(params("split=1")).split).toBe(32);
  });

  it("rejects non-numeric pages", () => {
    expect(parseView(params("page=abc")).page).toBeNull();
  });
});

describe("writeView", () => {
  it("round-trips a populated view", () => {
    const view = {doc:"NEP-2027-VOLUME-2B", tree:"pap", page:115, node:"r1",
                  zoom:{mode:"custom", percent:150}, split:66, overlay:"hide", pane:"pdf"};
    const out = writeView(new URLSearchParams(), view).toString();
    const parsed = parseView(params(out));
    expect(parsed).toEqual({...view, node:"r1"});
  });

  it("omits default values", () => {
    const out = writeView(new URLSearchParams(), {
      doc:"", tree:"", page:null, node:"", zoom:{mode:"fit", percent:100}, split:58,
      overlay:"hide", pane:"data",
    });
    expect(out.toString()).toBe("");
  });
});
