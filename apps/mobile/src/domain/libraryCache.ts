import type { Library, LibraryImage } from "../api/client";

type Page = { images: LibraryImage[]; hasMore: boolean };

export class LibraryCache {
  libraries: Library[] | null = null;
  selectedId: string | null = null;
  private readonly pages = new Map<string, Page>();

  get(id: string): Page | undefined {
    const page = this.pages.get(id);
    if (page) {
      this.pages.delete(id);
      this.pages.set(id, page);
    }
    return page;
  }

  set(id: string, images: LibraryImage[], hasMore: boolean): void {
    this.pages.delete(id);
    this.pages.set(id, { images: images.slice(0, 50), hasMore });
    if (this.pages.size > 3) this.pages.delete(this.pages.keys().next().value!);
  }

  reconcile(libraries: Library[]): void {
    this.libraries = libraries;
    for (const id of this.pages.keys()) {
      if (!libraries.some((library) => library.id === id)) this.pages.delete(id);
    }
    if (!libraries.some((library) => library.id === this.selectedId)) this.selectedId = libraries[0]?.id ?? null;
  }
}
