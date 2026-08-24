import {describe, expect, it} from "vitest";
import {
  nodeAnatomyChips,
  nodeLabelDescription,
  nodeLabelTitle,
  nodeLabelTooltip,
  nodeSearchText,
} from "./treeLabelDisplay.js";

describe("treeLabelDisplay", () => {
  it("shows stripped title with OCR tooltip", () => {
    const node = {
      label: "Maharlika Highway (LZ )",
      label_ocr: "Maharlika Highway (LZ ) - K0028+150 - K0031+420",
      chainages: [{kind: "K", from: "0028+150", to: "0031+420"}],
    };
    expect(nodeLabelTitle(node)).toBe("Maharlika Highway (LZ )");
    expect(nodeLabelTooltip(node)).toContain("K0028+150");
    expect(nodeAnatomyChips(node).chainages).toHaveLength(1);
  });

  it("includes description and anatomy in search text", () => {
    const node = {
      label: "Asset Preservation Program",
      description: "The program aims to improve national roads.",
      chainages: [{kind: "K", from: "0028+150", to: "0031+420"}],
      coordinates: [{lat: 14.1, lon: 121.2}],
    };
    expect(nodeLabelDescription(node)).toContain("program aims");
    const haystack = nodeSearchText(node).toLowerCase();
    expect(haystack).toContain("asset preservation");
    expect(haystack).toContain("program aims");
    expect(haystack).toContain("0028+150");
    expect(haystack).toContain("14.1");
  });
});
