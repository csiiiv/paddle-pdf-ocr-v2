import {describe, expect, it} from "vitest";
import {
  buildDocumentOrderRows,
  buildHierarchyIndex,
  parentId,
} from "./treeHierarchy.js";

const nodes = [
  {id: "root", parent_pdf: null, parent_prexc: null, label: "root"},
  {id: "a", parent_pdf: "root", parent_prexc: "root", label: "A"},
  {id: "b", parent_pdf: "root", parent_prexc: "a", label: "B"},
  {id: "c", parent_pdf: "a", parent_prexc: "a", label: "C"},
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
});
