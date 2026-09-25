import { describe, expect, it } from "vitest";
import { LibraryCache } from "../src/domain/libraryCache";
import type { LibraryImage } from "../src/api/client";

const image = (id: string): LibraryImage => ({ id, name: id, relative_path: id, mime_type: "image/png", size: 1, mtime: 1, thumbnail_url: `/thumb/${id}`, content_url: `/image/${id}` });

describe("LibraryCache", () => {
  it("restores the selected directory and its first page, including empty results", () => {
    const cache = new LibraryCache();
    cache.libraries = [{ id: "a", name: "A", recursive: false }];
    cache.selectedId = "a";
    cache.set("a", [image("one")], true);
    expect(cache.get("a")?.images.map((item) => item.id)).toEqual(["one"]);
    cache.set("a", [], false);
    expect(cache.get("a")).toEqual({ images: [], hasMore: false });
    expect(new LibraryCache().get("a")).toBeUndefined();
  });

  it("keeps only three directories and at most 50 images per directory", () => {
    const cache = new LibraryCache();
    cache.set("a", Array.from({ length: 60 }, (_, index) => image(String(index))), true);
    expect(cache.get("a")?.images).toHaveLength(50);
    cache.set("b", [], false);
    cache.set("c", [], false);
    cache.set("d", [], false);
    expect(cache.get("a")).toBeUndefined();
    expect(cache.get("b")).toBeDefined();
  });

  it("drops directories removed by the server", () => {
    const cache = new LibraryCache();
    cache.set("a", [image("old")], false);
    cache.selectedId = "a";
    cache.reconcile([{ id: "b", name: "B", recursive: false }]);
    expect(cache.get("a")).toBeUndefined();
    expect(cache.selectedId).toBe("b");
  });
});
