import { describe, expect, it } from "vitest";
import { shouldRefreshArtifacts } from "../src/domain/jobRefresh";
import type { GenerationJob } from "../src/api/client";

const job = (id: string, status: string): GenerationJob => ({ id, kind: "image", status, artifacts: [] });

describe("artifact refresh trigger", () => {
  it("refreshes when a job first appears as succeeded or becomes succeeded", () => {
    expect(shouldRefreshArtifacts([], [job("a", "succeeded")])).toBe(true);
    expect(shouldRefreshArtifacts([job("a", "running")], [job("a", "succeeded")])).toBe(true);
    expect(shouldRefreshArtifacts([job("a", "succeeded")], [job("a", "succeeded")])).toBe(false);
    expect(shouldRefreshArtifacts([job("a", "running")], [job("a", "failed")])).toBe(false);
  });
});
