import {describe, expect, it} from "vitest";
import {colGripGutter, colWidth} from "./treeTableLayout.js";

describe("treeTableLayout", () => {
  it("adds grip gutter to content widths", () => {
    expect(colGripGutter(false)).toBe(30);
    expect(colGripGutter(true)).toBe(36);
    expect(colWidth(120, false)).toBe(150);
  });
});
