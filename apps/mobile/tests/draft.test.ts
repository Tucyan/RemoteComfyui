import { describe, expect, it } from "vitest";
import {
  COMMON_VIDEO_FRAMES,
  VIDEO_PRESETS,
  insertPictureToken,
  moveReference,
  normalizeReferences,
  renumberPictureTokens,
  validateReferenceCount,
  validateVideoSettings,
  calculateVideoDimensions,
  adjustVideoFrames,
  formatElapsed,
  VIDEO_RATIOS,
  updateModePrompt,
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
    expect(COMMON_VIDEO_FRAMES).toEqual([5, 22, 39, 124, 175, 243, 294, 362]);
    expect(validateVideoSettings("portrait_low", 124)).toEqual({
      ok: true,
      width: 352,
      height: 608,
    });
    expect(validateVideoSettings("portrait_low", 125).ok).toBe(false);
    expect(validateVideoSettings("unknown", 124).ok).toBe(false);
  });

  it("offers seven ratios and 32-aligned dimensions for a target megapixel count", () => {
    expect(Object.keys(VIDEO_RATIOS)).toEqual(["2:3", "3:4", "9:16", "1:1", "16:9", "4:3", "3:2"]);
    expect(calculateVideoDimensions("16:9", 1.0)).toEqual(expect.objectContaining({ width: expect.any(Number), height: expect.any(Number) }));
    const size = calculateVideoDimensions("9:16", 1.5);
    expect(size.width % 32).toBe(0);
    expect(size.height % 32).toBe(0);
    expect(size.width).toBeLessThanOrEqual(1920);
    expect(size.height).toBeLessThanOrEqual(1088);
  });

  it("validates custom dimensions and advances frames by one workflow step", () => {
    expect(validateVideoSettings(640, 960, 5)).toEqual({ ok: true, width: 640, height: 960 });
    expect(validateVideoSettings(640, 960, 22)).toEqual({ ok: true, width: 640, height: 960 });
    expect(validateVideoSettings(640, 960, 4).ok).toBe(false);
    expect(validateVideoSettings(640, 960, 6).ok).toBe(false);
    expect(validateVideoSettings(640, 960, 141)).toEqual({ ok: true, width: 640, height: 960 });
    expect(validateVideoSettings(641, 960, 141).ok).toBe(false);
    expect(validateVideoSettings(640, 960, 140).ok).toBe(false);
    expect(adjustVideoFrames(124, 1)).toBe(141);
    expect(adjustVideoFrames(141, -1)).toBe(124);
    expect(adjustVideoFrames(124, -1)).toBe(107);
    expect(adjustVideoFrames(22, -1)).toBe(5);
    expect(adjustVideoFrames(5, -1)).toBe(5);
    expect(adjustVideoFrames(362, 1)).toBe(362);
  });

  it("formats running elapsed time in seconds or minutes and seconds", () => {
    expect(formatElapsed(20, 54)).toBe("已花费 34 秒");
    expect(formatElapsed(20, 145)).toBe("已花费 2 分 5 秒");
  });

  it("keeps image and video prompts independent when switching modes", () => {
    const first = updateModePrompt({ image: "", video: "" }, "image", "edit this");
    const second = updateModePrompt(first, "video", "animate this");
    expect(second).toEqual({ image: "edit this", video: "animate this" });
  });
});
