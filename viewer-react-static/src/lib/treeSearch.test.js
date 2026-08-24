import {describe, expect, it} from "vitest";
import {buildSearchIncluded, isNodeInSearchResults, isSearchFilterActive} from "./treeSearch.js";

const nodes = [
  {id: "root", parent: null, label: "Root", kind: "table_root", page: 1},
  {id: "a", parent: "root", label: "Alpha program", kind: "program", page: 2},
  {id: "b", parent: "a", label: "Beta bridge", kind: "project", page: 2},
  {id: "c", parent: "a", label: "Gamma road", kind: "project", page: 2},
];

describe("treeSearch", () => {
  it("returns null when search is inactive", () => {
    expect(buildSearchIncluded(nodes, {})).toBeNull();
    expect(isSearchFilterActive({})).toBe(false);
  });

  it("includes matches and their ancestors", () => {
    const included = buildSearchIncluded(nodes, {query: "beta"});
    expect(included?.has("b")).toBe(true);
    expect(included?.has("a")).toBe(true);
    expect(included?.has("c")).toBe(false);
  });

  it("detects nodes outside search results", () => {
    const included = buildSearchIncluded(nodes, {query: "beta"});
    expect(isNodeInSearchResults("b", included)).toBe(true);
    expect(isNodeInSearchResults("c", included)).toBe(false);
  });
});
