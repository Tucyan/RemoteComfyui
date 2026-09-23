export type GenerationMode = "image" | "video";
export type WorkflowId = "qwen_edit_2511" | "qwen_image_2_1_8gb_edit" | "qwen_image_2_1_8gb_t2i" | "minimax_h3";
export type WorkflowDescriptor = { label: string; description: string; kind: GenerationMode; minReferences: number; maxReferences: number };

export const WORKFLOW_DESCRIPTORS: Record<WorkflowId, WorkflowDescriptor> = {
  qwen_edit_2511: { label: "Qwen Edit 2511", description: "使用 1–3 张参考图进行编辑", kind: "image", minReferences: 1, maxReferences: 3 },
  qwen_image_2_1_8gb_edit: { label: "Qwen Image 2.1 Edit · 8GB", description: "基于首张目标图编辑，可添加最多 9 张参考图", kind: "image", minReferences: 1, maxReferences: 10 },
  qwen_image_2_1_8gb_t2i: { label: "Qwen Image 2.1 文生图 · 8GB", description: "只根据文字生成图片", kind: "image", minReferences: 0, maxReferences: 0 },
  minimax_h3: { label: "MiniMax H3 视频", description: "使用 1–9 张参考图生成视频", kind: "video", minReferences: 1, maxReferences: 9 },
};

export const QWEN_EDIT_SCALE = { min: 0.5, max: 2, step: 0.1, initial: 1 } as const;
export const QWEN_IMAGE_MAX_SIDE = 2048;

export function updateModePrompt(prompts: Record<GenerationMode, string>, mode: GenerationMode, value: string): Record<GenerationMode, string> {
  return { ...prompts, [mode]: value };
}

export function updateWorkflowPrompt(prompts: Record<WorkflowId, string>, workflow: WorkflowId, value: string): Record<WorkflowId, string> {
  return { ...prompts, [workflow]: value };
}

export function updateWorkflowValue<T>(values: Record<WorkflowId, T>, workflow: WorkflowId, value: T): Record<WorkflowId, T> {
  return { ...values, [workflow]: value };
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

export function validateReferenceCount(workflow: WorkflowId, count: number): boolean {
  const descriptor = WORKFLOW_DESCRIPTORS[workflow];
  return Number.isInteger(count) && count >= descriptor.minReferences && count <= descriptor.maxReferences;
}

function alignedPair(width: number, height: number, multiple: number, maxSide: number): { width: number; height: number; adjusted: boolean } {
  if (!Number.isFinite(width) || !Number.isFinite(height) || width <= 0 || height <= 0 || width > maxSide || height > maxSide) {
    throw new Error(`宽度和高度必须在 1～${maxSide} 之间`);
  }
  const targetRatio = width / height;
  const centerWidth = Math.round(width / multiple);
  const centerHeight = Math.round(height / multiple);
  let best: { width: number; height: number; ratioError: number; areaError: number } | undefined;
  for (let wi = Math.max(1, centerWidth - 4); wi <= centerWidth + 4; wi++) {
    for (let hi = Math.max(1, centerHeight - 4); hi <= centerHeight + 4; hi++) {
      const candidateWidth = wi * multiple;
      const candidateHeight = hi * multiple;
      if (candidateWidth > maxSide || candidateHeight > maxSide) continue;
      const ratioError = Math.abs(Math.log((candidateWidth / candidateHeight) / targetRatio));
      const areaError = Math.abs(candidateWidth * candidateHeight - width * height);
      if (!best || ratioError < best.ratioError - 1e-12 || (Math.abs(ratioError - best.ratioError) <= 1e-12 && areaError < best.areaError)) {
        best = { width: candidateWidth, height: candidateHeight, ratioError, areaError };
      }
    }
  }
  if (!best) throw new Error(`尺寸无法对齐到 ${multiple} 的倍数并保持在 ${maxSide} 以内`);
  return { width: best.width, height: best.height, adjusted: best.width !== width || best.height !== height };
}

export function calculateEditDimensions(sourceWidth: number, sourceHeight: number, scaleFactor: number): { width: number; height: number; adjusted: boolean } {
  if (!Number.isInteger(sourceWidth) || !Number.isInteger(sourceHeight) || sourceWidth <= 0 || sourceHeight <= 0) throw new Error("参考图尺寸无效");
  if (!Number.isFinite(scaleFactor) || scaleFactor < QWEN_EDIT_SCALE.min || scaleFactor > QWEN_EDIT_SCALE.max) throw new Error("编辑倍率必须在 0.5×～2.0× 之间");
  const requestedWidth = sourceWidth * scaleFactor;
  const requestedHeight = sourceHeight * scaleFactor;
  const width = Math.max(32, Math.round(requestedWidth / 32) * 32);
  const height = Math.max(32, Math.round(requestedHeight / 32) * 32);
  if (width > QWEN_IMAGE_MAX_SIDE || height > QWEN_IMAGE_MAX_SIDE) throw new Error(`宽度和高度必须在 1～${QWEN_IMAGE_MAX_SIDE} 之间`);
  return { width, height, adjusted: width !== requestedWidth || height !== requestedHeight };
}

export function initialEditScale(sourceWidth: number, sourceHeight: number): number {
  if (!Number.isInteger(sourceWidth) || !Number.isInteger(sourceHeight) || sourceWidth <= 0 || sourceHeight <= 0) throw new Error("参考图尺寸无效");
  try { calculateEditDimensions(sourceWidth, sourceHeight, QWEN_EDIT_SCALE.initial); return QWEN_EDIT_SCALE.initial; } catch { /* choose the largest supported slider step */ }
  const fit = Math.min(QWEN_IMAGE_MAX_SIDE / sourceWidth, QWEN_IMAGE_MAX_SIDE / sourceHeight, QWEN_EDIT_SCALE.initial);
  return Math.max(QWEN_EDIT_SCALE.min, Math.floor(fit * 10 + 1e-9) / 10);
}

export function lockEditDimensions(sourceWidth: number, sourceHeight: number, changed: "width" | "height", value: number): { width: number; height: number; adjusted: boolean } {
  if (!Number.isFinite(value) || value <= 0) throw new Error("宽度和高度必须是正数");
  if (!Number.isInteger(sourceWidth) || !Number.isInteger(sourceHeight) || sourceWidth <= 0 || sourceHeight <= 0) throw new Error("参考图尺寸无效");
  const alignedChanged = Math.max(32, Math.round(value / 32) * 32);
  const requestedWidth = changed === "width" ? value : value * sourceWidth / sourceHeight;
  const width = changed === "width" ? alignedChanged : Math.max(32, Math.round(alignedChanged * sourceWidth / sourceHeight / 32) * 32);
  // The server derives the final height from the submitted width; use the same rounding here.
  const height = Math.max(32, Math.floor((width * sourceHeight / sourceWidth) / 32 + 0.5) * 32);
  if (width > QWEN_IMAGE_MAX_SIDE || height > QWEN_IMAGE_MAX_SIDE) throw new Error(`宽度和高度必须在 1～${QWEN_IMAGE_MAX_SIDE} 之间`);
  const requestedHeight = changed === "height" ? value : value * sourceHeight / sourceWidth;
  return { width, height, adjusted: width !== requestedWidth || height !== requestedHeight };
}

export function calculateImageDimensions(ratio: string, megapixels: number): { width: number; height: number; adjusted: boolean } {
  const parts = VIDEO_RATIOS[ratio];
  if (!parts || !Number.isFinite(megapixels) || megapixels < 0.2 || megapixels > 1.5) throw new Error("无效的图片清晰度或比例");
  const area = megapixels * 1_000_000;
  const width = Math.sqrt(area * parts[0] / parts[1]);
  const height = Math.sqrt(area * parts[1] / parts[0]);
  return alignedPair(width, height, 8, QWEN_IMAGE_MAX_SIDE);
}

export function normalizeImageDimensions(width: number, height: number): { width: number; height: number; adjusted: boolean } {
  return alignedPair(width, height, 8, QWEN_IMAGE_MAX_SIDE);
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
