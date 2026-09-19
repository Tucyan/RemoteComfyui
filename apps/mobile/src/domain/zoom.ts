export type TouchPoint = { pageX: number; pageY: number };

export function touchDistance(touches: readonly TouchPoint[]): number | null {
  if (touches.length < 2) return null;
  return Math.hypot(touches[0].pageX - touches[1].pageX, touches[0].pageY - touches[1].pageY);
}

export function clampZoom(scale: number): number {
  return Math.min(4, Math.max(1, Number.isFinite(scale) ? scale : 1));
}
