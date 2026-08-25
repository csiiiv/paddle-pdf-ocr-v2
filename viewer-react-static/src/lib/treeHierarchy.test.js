import {describe, expect, it} from "vitest";
import {
  buildDocumentOrderRows,
  buildHierarchyIndex,
  collectExpandAncestors,
  isRowVisible,
  parentId,
  withExpandedAncestors,
} from "./treeHierarchy.js";

const nodes = [
  {id: "root", parent_pdf: null, parent_prexc: null, label: "root"},
  {id: "a", parent_pdf: "root", parent_prexc: "root", label: "A"},
  {id: "b", parent_pdf: "root", parent_prexc: "a", label: "B"},
  {id: "c", parent_pdf: "a", parent_prexc: "a", label: "C"},
];

const legacyNodes = [
  {id: "root", parent: null, children: ["a"], label: "root"},
  {id: "a", parent: "root", children: ["b", "c"], label: "A"},
  {id: "b", parent: "a", children: [], label: "B"},
  {id: "c", parent: "a", children: [], label: "C"},
];

describe("treeHierarchy", () => {
  it("keeps document order regardless of hierarchy mode", () => {
    const expanded = new Set(["root", "a", "b", "c"]);
    const pdfRows = buildDocumentOrderRows(nodes, "pdf", expanded, null);
    const prexcRows = buildDocumentOrderRows(nodes, "prexc", expanded, null);
    expect(pdfRows.map((row) => row.node.id)).toEqual(["root", "a", "b", "c"]);
    expect(prexcRows.map((row) => row.node.id)).toEqual(["root", "a", "b", "c"]);
  });

  it("changes depth by hierarchy mode", () => {
    const {depth: pdfDepth} = buildHierarchyIndex(nodes, "pdf");
    const {depth: prexcDepth} = buildHierarchyIndex(nodes, "prexc");
    expect(pdfDepth.get("b")).toBe(1);
    expect(prexcDepth.get("b")).toBe(2);
    expect(parentId(nodes[2], "prexc")).toBe("a");
  });

  it("hides descendants when a parent is collapsed, even under a search filter", () => {
    const byId = new Map(nodes.map((node) => [node.id, node]));
    const included = new Set(["root", "a", "b", "c"]);
    const expanded = new Set(["root"]); // a collapsed → b/c hidden in prexc
    expect(isRowVisible("a", byId, "prexc", expanded, included)).toBe(true);
    expect(isRowVisible("b", byId, "prexc", expanded, included)).toBe(false);
    expect(isRowVisible("c", byId, "prexc", expanded, included)).toBe(false);
    const rows = buildDocumentOrderRows(nodes, "prexc", expanded, included);
    expect(rows.map((row) => row.node.id)).toEqual(["root", "a"]);
  });

  it("collects ancestor ids for dual and legacy trees", () => {
    const dualById = new Map(nodes.map((node) => [node.id, node]));
    expect([...collectExpandAncestors(["b"], dualById, {
      dualHierarchy: true,
      hierarchyMode: "prexc",
    })].sort()).toEqual(["a", "root"]);

    const legacyById = new Map(legacyNodes.map((node) => [node.id, node]));
    expect([...collectExpandAncestors(["b", "c"], legacyById)].sort())
      .toEqual(["a", "root"]);
  });

  it("withExpandedAncestors returns the same set when already complete", () => {
    const expanded = new Set(["root", "a"]);
    expect(withExpandedAncestors(expanded, new Set(["root", "a"]))).toBe(expanded);
    const next = withExpandedAncestors(expanded, new Set(["root", "a", "b"]));
    expect(next).not.toBe(expanded);
    expect(next.has("b")).toBe(true);
  });
});
