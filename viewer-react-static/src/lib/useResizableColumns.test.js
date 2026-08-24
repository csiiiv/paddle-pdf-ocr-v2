import {describe, expect, it, vi} from "vitest";
import {renderHook, act} from "@testing-library/react";
import {useResizableColumns} from "./useResizableColumns.js";

const columns = [
  {key: "label", default: 360, min: 180},
  {key: "kind", default: 110, min: 72},
];

describe("useResizableColumns", () => {
  it("starts from default widths", () => {
    const {result} = renderHook(() => useResizableColumns(columns));
    expect(result.current.widths).toEqual({label: 360, kind: 110});
    expect(result.current.totalWidth).toBe(470);
  });

  it("updates width while dragging", () => {
    const {result} = renderHook(() => useResizableColumns(columns));
    const handle = {
      setPointerCapture: vi.fn(),
      releasePointerCapture: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    };
    const event = {
      pointerId: 1,
      clientX: 100,
      preventDefault: vi.fn(),
      stopPropagation: vi.fn(),
      currentTarget: handle,
    };

    act(() => {
      result.current.startResize("label", event);
    });

    const onMove = handle.addEventListener.mock.calls.find(([name]) => name === "pointermove")[1];
    act(() => {
      onMove({pointerId: 1, clientX: 140});
    });
    expect(result.current.widths.label).toBe(400);
  });
});
