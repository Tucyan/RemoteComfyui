import type { GenerationJob } from "../api/client";

export function shouldRefreshArtifacts(previous: GenerationJob[], next: GenerationJob[]): boolean {
  const completed = new Set(previous.filter((job) => job.status === "succeeded").map((job) => job.id));
  return next.some((job) => job.status === "succeeded" && !completed.has(job.id));
}
