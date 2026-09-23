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
  normalizeVideoDimensions,
  calculateVideoDimensions,
  adjustVideoFrames,
  formatElapsed,
  VIDEO_RATIOS,
  updateModePrompt,
  WORKFLOW_DESCRIPTORS,
  calculateEditDimensions,
  lockEditDimensions,
  calculateImageDimensions,
  updateWorkflowPrompt,
  initialEditScale,
  updateWorkflowValue,
} from "../src/domain/draft";

describe("mobile generation draft", () => {
  it("accepts Qwen references from one to three and rejects other counts", () => {
    expect(validateReferenceCount("qwen_edit_2511", 1)).toBe(true);
    expect(validateReferenceCount("qwen_edit_2511", 3)).toBe(true);
    expect(validateReferenceCount("qwen_edit_2511", 0)).toBe(false);
    expect(validateReferenceCount("qwen_edit_2511", 4)).toBe(false);
    expect(validateReferenceCount("qwen_image_2_1_8gb_edit", 10)).toBe(true);
    expect(validateReferenceCount("qwen_image_2_1_8gb_edit", 11)).toBe(false);
    expect(validateReferenceCount("qwen_image_2_1_8gb_t2i", 0)).toBe(true);
    expect(validateReferenceCount("qwen_image_2_1_8gb_t2i", 1)).toBe(false);
    expect(validateReferenceCount("minimax_h3", 9)).toBe(true);
    expect(validateReferenceCount("minimax_h3", 10)).toBe(false);
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
    expect(size.width * size.height).toBeGreaterThan(1_400_000);
  });

  it("validates custom dimensions and advances frames by one workflow step", () => {
    expect(validateVideoSettings(640, 960, 5)).toEqual({ ok: true, width: 640, height: 960 });
    expect(validateVideoSettings(640, 960, 22)).toEqual({ ok: true, width: 640, height: 960 });
    expect(validateVideoSettings(640, 960, 4).ok).toBe(false);
    expect(validateVideoSettings(640, 960, 6).ok).toBe(false);
    expect(validateVideoSettings(640, 960, 141)).toEqual({ ok: true, width: 640, height: 960 });
    expect(validateVideoSettings(641, 959, 141)).toEqual({ ok: true, width: 640, height: 960, adjusted: true });
    expect(validateVideoSettings(640, 960, 140).ok).toBe(false);
    expect(adjustVideoFrames(124, 1)).toBe(141);
    expect(adjustVideoFrames(141, -1)).toBe(124);
    expect(adjustVideoFrames(124, -1)).toBe(107);
    expect(adjustVideoFrames(22, -1)).toBe(5);
    expect(adjustVideoFrames(5, -1)).toBe(5);
    expect(adjustVideoFrames(362, 1)).toBe(362);
  });

  it("snaps free-form dimensions to the nearest safe 32-aligned values", () => {
    expect(normalizeVideoDimensions(641, 959)).toEqual({ width: 640, height: 960, adjusted: true });
    expect(normalizeVideoDimensions(640, 960)).toEqual({ width: 640, height: 960, adjusted: false });
    expect(normalizeVideoDimensions(1, 4096)).toEqual({ width: 32, height: 4096, adjusted: true });
    expect(normalizeVideoDimensions(80, 112)).toEqual({ width: 96, height: 128, adjusted: true });
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

  it("describes four workflows with the correct kind and reference limits", () => {
    expect(Object.keys(WORKFLOW_DESCRIPTORS)).toEqual([
      "qwen_edit_2511", "qwen_image_2_1_8gb_edit", "qwen_image_2_1_8gb_t2i", "minimax_h3",
    ]);
    expect(WORKFLOW_DESCRIPTORS.qwen_image_2_1_8gb_t2i).toMatchObject({ kind: "image", minReferences: 0, maxReferences: 0 });
    expect(WORKFLOW_DESCRIPTORS.minimax_h3).toMatchObject({ kind: "video", minReferences: 1, maxReferences: 9 });
  });

  it("preserves independent prompts when switching among workflows", () => {
    const blank = { qwen_edit_2511: "", qwen_image_2_1_8gb_edit: "", qwen_image_2_1_8gb_t2i: "", minimax_h3: "" };
    const edit = updateWorkflowPrompt(blank, "qwen_image_2_1_8gb_edit", "edit prompt");
    const t2i = updateWorkflowPrompt(edit, "qwen_image_2_1_8gb_t2i", "draw prompt");
    const video = updateWorkflowPrompt(t2i, "minimax_h3", "video prompt");
    expect(video).toEqual({ qwen_edit_2511: "", qwen_image_2_1_8gb_edit: "edit prompt", qwen_image_2_1_8gb_t2i: "draw prompt", minimax_h3: "video prompt" });
  });

  it("preserves independent reference drafts while switching workflows", () => {
    const blank = { qwen_edit_2511: [] as string[], qwen_image_2_1_8gb_edit: [], qwen_image_2_1_8gb_t2i: [], minimax_h3: [] };
    const edit = updateWorkflowValue(blank, "qwen_image_2_1_8gb_edit", ["target", "reference"]);
    const video = updateWorkflowValue(edit, "minimax_h3", ["video-reference"]);
    expect(video.qwen_image_2_1_8gb_edit).toEqual(["target", "reference"]);
    expect(video.minimax_h3).toEqual(["video-reference"]);
    expect(video.qwen_image_2_1_8gb_t2i).toEqual([]);
    expect(edit.qwen_image_2_1_8gb_edit).toEqual(["target", "reference"]);
  });

  it("calculates edit dimensions at 0.5x, 1x, and 2x while preserving portrait and landscape ratios", () => {
    expect(calculateEditDimensions(1024, 768, 0.5)).toEqual({ width: 512, height: 384, adjusted: false });
    expect(calculateEditDimensions(1024, 768, 1)).toEqual({ width: 1024, height: 768, adjusted: false });
    expect(calculateEditDimensions(1024, 768, 2)).toEqual({ width: 2048, height: 1536, adjusted: false });
    const portrait = calculateEditDimensions(768, 1024, 1.1);
    const landscape = calculateEditDimensions(1536, 1024, 0.8);
    expect(portrait.width % 32).toBe(0);
    expect(portrait.height % 32).toBe(0);
    expect(Math.abs(portrait.width / portrait.height / (768 / 1024) - 1)).toBeLessThan(0.03);
    expect(Math.abs(landscape.width / landscape.height / (1536 / 1024) - 1)).toBeLessThan(0.03);
    expect(calculateEditDimensions(640, 480, 1.1)).toEqual({ width: 704, height: 544, adjusted: true });
    expect(initialEditScale(4000, 3000)).toBe(0.5);
    expect(calculateEditDimensions(4000, 3000, initialEditScale(4000, 3000))).toEqual({ width: 2016, height: 1504, adjusted: true });
  });

  it("keeps the edit aspect ratio when width or height changes and rejects unsafe bounds", () => {
    expect(lockEditDimensions(1200, 800, "width", 640)).toEqual({ width: 640, height: 416, adjusted: true });
    expect(lockEditDimensions(1200, 800, "height", 640)).toEqual({ width: 960, height: 640, adjusted: false });
    expect(() => calculateEditDimensions(4000, 3000, 1)).toThrow();
    expect(() => calculateEditDimensions(1000, 800, 0.4)).toThrow();
    expect(() => lockEditDimensions(1000, 800, "width", 0)).toThrow();
  });

  it("calculates T2I dimensions for each video ratio with 8-pixel alignment and a 2048 cap", () => {
    for (const ratio of Object.keys(VIDEO_RATIOS)) {
      const size = calculateImageDimensions(ratio, 1);
      expect(size.width % 8).toBe(0);
      expect(size.height % 8).toBe(0);
      expect(size.width).toBeLessThanOrEqual(2048);
      expect(size.height).toBeLessThanOrEqual(2048);
    }
    expect(() => calculateImageDimensions("bad", 1)).toThrow();
    expect(() => calculateImageDimensions("1:1", 2)).toThrow();
  });
});
