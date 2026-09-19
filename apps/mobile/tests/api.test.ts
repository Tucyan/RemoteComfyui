import { afterEach, describe, expect, it, vi } from "vitest";
import { RemoteApi } from "../src/api/client";

afterEach(() => vi.restoreAllMocks());

describe("mobile API client", () => {
  it("adds the bearer token and resolves relative media URLs", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ jobs: [] }), { status: 200 }),
    );
    const api = new RemoteApi("http://192.168.1.20:3000/", "rc_test");

    await expect(api.listJobs()).resolves.toEqual({ jobs: [] });
    expect(fetchMock).toHaveBeenCalledWith(
      "http://192.168.1.20:3000/api/v1/jobs",
      expect.objectContaining({ headers: { Authorization: "Bearer rc_test" } }),
    );
    expect(api.mediaUrl("/api/v1/artifacts/a/content")).toBe(
      "http://192.168.1.20:3000/api/v1/artifacts/a/content",
    );
  });

  it("sends image and video payloads using the public API field names", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async () =>
      new Response(JSON.stringify({ id: "job_1" }), { status: 202 }),
    );
    const api = new RemoteApi("http://gateway:3000", "rc_test");

    await api.createImageJob("prompt", ["asset_1"]);
    await api.createVideoJob("video", ["asset_1", "asset_2"], "portrait_low", 175);

    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      "http://gateway:3000/api/v1/jobs/image",
      expect.objectContaining({ body: JSON.stringify({ prompt: "prompt", referenceAssetIds: ["asset_1"] }) }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "http://gateway:3000/api/v1/jobs/video",
      expect.objectContaining({ body: JSON.stringify({ prompt: "video", referenceAssetIds: ["asset_1", "asset_2"], resolutionPreset: "portrait_low", frames: 175 }) }),
    );
  });

  it("imports a protected library image through the upload endpoint", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(new Response(new Blob(["image"], { type: "image/png" }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ assets: [{ id: "asset_2", filename: "desk.png", mime_type: "image/png", size: 5 }] }), { status: 200 }));
    const api = new RemoteApi("http://gateway:3000", "rc_test");

    await expect(api.importLibraryImage({
      id: "libimg_1",
      name: "desk.png",
      relative_path: "desk.png",
      mime_type: "image/png",
      size: 5,
      mtime: 1,
      thumbnail_url: "/thumb",
      content_url: "/content",
    })).resolves.toMatchObject({ id: "asset_2" });
    expect(fetchMock).toHaveBeenNthCalledWith(1, "http://gateway:3000/content", { headers: { Authorization: "Bearer rc_test" } });
  });
});
