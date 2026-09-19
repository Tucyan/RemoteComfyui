import { describe, expect, it } from "vitest";
import {
  VIDEO_FRAMES,
  VIDEO_PRESETS,
  insertPictureToken,
  moveReference,
  normalizeReferences,
  renumberPictureTokens,
  validateReferenceCount,
  validateVideoSettings,
} from "../src/domain/draft";

describe("mobile generation draft", () => {
  it("accepts Qwen references from one to three and rejects other counts", () => {
    expect(validateReferenceCount("image", 1)).toBe(true);
    expect(validateReferenceCount("image", 3)).toBe(true);
    expect(validateReferenceCount("image", 0)).toBe(false);
    expect(validateReferenceCount("image", 4)).toBe(false);
    expect(validateReferenceCount("video", 9)).toBe(true);
    expect(validateReferenceCount("video", 10)).toBe(false);
  });

  it("keeps valid picture tokens and clamps them after references are removed", () => {
    expect(renumberPictureTokens("A <Picture 3> then <Picture 1>.", ["b", "c", "a"]))
      .toBe("A <Picture 3> then <Picture 1>.");
    expect(insertPictureToken("before", 2)).toBe("before <Picture 2>");
    expect(moveReference(["a", "b", "c"], 2, 0)).toEqual(["c", "a", "b"]);
  });

  it("keeps reference list stable when a deleted item leaves stale tokens", () => {
    expect(normalizeReferences(["a", "", "b"])).toEqual(["a", "b"]);
    expect(renumberPictureTokens("<Picture 1> <Picture 3>", ["a", "b"]))
      .toBe("<Picture 1> <Picture 2>");
  });

  it("validates only the supported video presets and 17n+5 frames", () => {
    expect(Object.keys(VIDEO_PRESETS)).toContain("portrait_low");
    expect(VIDEO_FRAMES).toEqual([124, 175, 243, 294, 362]);
    expect(validateVideoSettings("portrait_low", 124)).toEqual({
      ok: true,
      width: 352,
      height: 608,
    });
    expect(validateVideoSettings("portrait_low", 125).ok).toBe(false);
    expect(validateVideoSettings("unknown", 124).ok).toBe(false);
  });
});
