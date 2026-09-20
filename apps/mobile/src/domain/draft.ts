export type GenerationMode = "image" | "video";

export function updateModePrompt(prompts: Record<GenerationMode, string>, mode: GenerationMode, value: string): Record<GenerationMode, string> {
  return { ...prompts, [mode]: value };
}

export const VIDEO_PRESETS: Record<string, { width: number; height: number; label: string }> = {
  portrait_low: { width: 352, height: 608, label: "竖屏低负载" },
  landscape_low: { width: 608, height: 352, label: "横屏低负载" },
  square_low: { width: 448, height: 448, label: "方形低负载" },
  portrait_standard: { width: 480, height: 864, label: "竖屏标准" },
  landscape_standard: { width: 864, height: 480, label: "横屏标准" },
  square_standard: { width: 640, height: 640, label: "方形标准" },
};

export const COMMON_VIDEO_FRAMES = [5, 22, 39, 124, 175, 243, 294, 362] as const;
export const VIDEO_RATIOS: Record<string, [number, number]> = {
  "2:3": [2, 3], "3:4": [3, 4], "9:16": [9, 16], "1:1": [1, 1],
  "16:9": [16, 9], "4:3": [4, 3], "3:2": [3, 2],
};

export function calculateVideoDimensions(ratio: string, megapixels: number): { width: number; height: number } {
  const parts = VIDEO_RATIOS[ratio];
  if (!parts || !Number.isFinite(megapixels) || megapixels < 0.2 || megapixels > 1.5) throw new Error("无效的视频清晰度或比例");
  const area = megapixels * 1_000_000;
  const width = Math.sqrt(area * parts[0] / parts[1]);
  const height = Math.sqrt(area * parts[1] / parts[0]);
  return normalizeVideoDimensions(width, height);
}

export function normalizeVideoDimensions(width: number, height: number): { width: number; height: number; adjusted: boolean } {
  if (!Number.isFinite(width) || !Number.isFinite(height) || width <= 0 || height <= 0) {
    throw new Error("宽度和高度必须是正数");
  }
  const normalizedWidth = Math.max(32, Math.round(width / 32) * 32);
  const normalizedHeight = Math.max(32, Math.round(height / 32) * 32);
  return { width: normalizedWidth, height: normalizedHeight, adjusted: normalizedWidth !== width || normalizedHeight !== height };
}

export function adjustVideoFrames(frames: number, direction: -1 | 1): number {
  const current = Number.isFinite(frames) ? frames : 124;
  const step = direction > 0 ? Math.floor((current - 5) / 17) + 1 : Math.ceil((current - 5) / 17) - 1;
  return Math.max(5, Math.min(362, step * 17 + 5));
}

export function formatElapsed(startSeconds: number, nowSeconds: number): string {
  const elapsed = Math.max(0, Math.floor(nowSeconds - startSeconds));
  if (elapsed < 60) return `已花费 ${elapsed} 秒`;
  return `已花费 ${Math.floor(elapsed / 60)} 分 ${elapsed % 60} 秒`;
}

export function validateReferenceCount(mode: GenerationMode, count: number): boolean {
  return Number.isInteger(count) && count >= 1 && count <= (mode === "image" ? 3 : 9);
}

export function normalizeReferences(references: string[]): string[] {
  return references.filter((reference) => reference.trim().length > 0);
}

export function moveReference<T>(references: T[], from: number, to: number): T[] {
  if (from < 0 || from >= references.length || to < 0 || to >= references.length || from === to) {
    return [...references];
  }
  const next = [...references];
  const [item] = next.splice(from, 1);
  next.splice(to, 0, item);
  return next;
}

export function insertPictureToken(prompt: string, position: number): string {
  const token = `<Picture ${Math.max(1, Math.floor(position))}>`;
  const separator = prompt.trim().length > 0 ? " " : "";
  return `${prompt.trimEnd()}${separator}${token}`;
}

export function renumberPictureTokens(prompt: string, references: string[]): string {
  const count = references.length;
  if (count === 0) return prompt.replace(/<Picture\s+\d+>/gi, "");
  return prompt.replace(/<Picture\s+(\d+)>/gi, (_match, rawIndex: string) => {
    const index = Number(rawIndex);
    if (!Number.isInteger(index) || index < 1) return "<Picture 1>";
    return `<Picture ${Math.min(index, count)}>`;
  });
}

export function validateVideoSettings(
  widthOrPreset: number | string,
  heightOrFrames: number,
  frames?: number,
): { ok: true; width: number; height: number; adjusted?: true } | { ok: false; error: string } {
  const selected = typeof widthOrPreset === "string" ? VIDEO_PRESETS[widthOrPreset] : { width: widthOrPreset, height: heightOrFrames };
  if (!selected) return { ok: false, error: "不支持的分辨率预设" };
  const count = typeof widthOrPreset === "string" ? heightOrFrames : frames;
  let dimensions;
  try { dimensions = normalizeVideoDimensions(selected.width, selected.height); }
  catch (cause) { return { ok: false, error: cause instanceof Error ? cause.message : "无效的视频尺寸" }; }
  if (!Number.isInteger(count) || count! < 5 || count! > 362 || (count! - 5) % 17 !== 0) {
    return { ok: false, error: "帧数须为 5～362 且满足 17n+5" };
  }
  return dimensions.adjusted
    ? { ok: true, width: dimensions.width, height: dimensions.height, adjusted: true }
    : { ok: true, width: dimensions.width, height: dimensions.height };
}
