import {describe, expect, it} from "vitest";
import {formatChainageChip, formatGpsChip} from "./papLabelChips.js";

describe("papLabelChips", () => {
  it("formats a chainage range", () => {
    expect(formatChainageChip({kind: "K", from: "0028+150", to: "0031+420"}))
      .toBe("K 0028+150 → 0031+420");
  });

  it("formats a GPS coordinate", () => {
    expect(formatGpsChip({lat: 14.701817, lon: 120.928578}))
      .toBe("14.70182, 120.92858");
  });
});
