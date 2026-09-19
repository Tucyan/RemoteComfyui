export type GenerationMode = "image" | "video";

export const VIDEO_PRESETS: Record<string, { width: number; height: number; label: string }> = {
  portrait_low: { width: 352, height: 608, label: "竖屏低负载" },
  landscape_low: { width: 608, height: 352, label: "横屏低负载" },
  square_low: { width: 448, height: 448, label: "方形低负载" },
  portrait_standard: { width: 480, height: 864, label: "竖屏标准" },
  landscape_standard: { width: 864, height: 480, label: "横屏标准" },
  square_standard: { width: 640, height: 640, label: "方形标准" },
};

export const VIDEO_FRAMES = [124, 175, 243, 294, 362] as const;

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
  preset: string,
  frames: number,
): { ok: true; width: number; height: number } | { ok: false; error: string } {
  const selected = VIDEO_PRESETS[preset];
  if (!selected) return { ok: false, error: "不支持的分辨率预设" };
  if (!VIDEO_FRAMES.includes(frames as (typeof VIDEO_FRAMES)[number])) {
    return { ok: false, error: "帧数必须使用预设值" };
  }
  return { ok: true, width: selected.width, height: selected.height };
}
