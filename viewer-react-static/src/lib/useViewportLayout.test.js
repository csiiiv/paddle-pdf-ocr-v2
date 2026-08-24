import {describe, expect, it, vi, afterEach} from "vitest";
import {computeViewportLayout} from "./useViewportLayout.js";

describe("computeViewportLayout", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("treats short touch landscape as mobile (tabbed, not desktop split)", () => {
    vi.stubGlobal("matchMedia", vi.fn(() => ({matches: true})));
    vi.stubGlobal("innerWidth", 844);
    vi.stubGlobal("innerHeight", 390);
    const layout = computeViewportLayout();
    expect(layout.isMobile).toBe(true);
    expect(layout.landscape).toBe(true);
  });

  it("treats narrow portrait as mobile", () => {
    vi.stubGlobal("matchMedia", vi.fn(() => ({matches: true})));
    vi.stubGlobal("innerWidth", 390);
    vi.stubGlobal("innerHeight", 844);
    const layout = computeViewportLayout();
    expect(layout.isMobile).toBe(true);
    expect(layout.landscape).toBe(false);
  });
});
