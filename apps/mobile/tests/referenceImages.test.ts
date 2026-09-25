import { describe, expect, it } from "vitest";
import { RemoteApi, type LibraryImage } from "../src/api/client";
import { libraryReferenceSources, phoneReferenceSources } from "../src/domain/referenceImages";

describe("reference image sources", () => {
  it("uses the selected phone image for both thumbnail and full preview", () => {
    expect(phoneReferenceSources("file:///picked/photo.jpg")).toEqual({
      thumbnailSource: { uri: "file:///picked/photo.jpg" },
      previewSource: { uri: "file:///picked/photo.jpg" },
    });
  });

  it("uses authenticated computer thumbnail and full image URLs", () => {
    const api = new RemoteApi("http://gateway:3000", "rc_test");
    const image: LibraryImage = {
      id: "libimg_1",
      name: "desk.png",
      relative_path: "desk.png",
      mime_type: "image/png",
      size: 5,
      mtime: 1,
      thumbnail_url: "/api/v1/library-images/libimg_1/thumbnail",
      content_url: "/api/v1/library-images/libimg_1/content",
    };

    expect(libraryReferenceSources(api, image)).toEqual({
      thumbnailSource: {
        uri: "http://gateway:3000/api/v1/library-images/libimg_1/thumbnail",
        headers: { Authorization: "Bearer rc_test" },
      },
      previewSource: {
        uri: "http://gateway:3000/api/v1/library-images/libimg_1/content",
        headers: { Authorization: "Bearer rc_test" },
      },
    });
  });
});
