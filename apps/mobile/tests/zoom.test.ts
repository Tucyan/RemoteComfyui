import { describe, expect, it } from "vitest";
import { clampZoom, touchDistance } from "../src/domain/zoom";

describe("pinch zoom", () => {
  it("measures two-finger distance", () => {
    expect(touchDistance([{ pageX: 0, pageY: 0 }, { pageX: 3, pageY: 4 }])).toBe(5);
    expect(touchDistance([{ pageX: 1, pageY: 1 }])).toBeNull();
  });

  it("clamps scale to a usable range", () => {
    expect(clampZoom(0.3)).toBe(1);
    expect(clampZoom(2.5)).toBe(2.5);
    expect(clampZoom(9)).toBe(4);
  });
});
