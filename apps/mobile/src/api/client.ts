import type { WorkflowId } from "../domain/draft";

export type GenerationJob = {
  id: string;
  kind: "image" | "video";
  workflow?: WorkflowId;
  status: string;
  prompt_id?: string | null;
  error?: string | null;
  created_at?: number;
  updated_at?: number;
  started_at?: number | null;
  artifacts: Artifact[];
};

export type Artifact = {
  id: string;
  job_id: string;
  mime_type: string;
  size: number;
  created_at: number;
};

export type Library = { id: string; name: string; recursive: boolean };
export type LibraryImage = {
  id: string;
  name: string;
  relative_path: string;
  mime_type: string;
  size: number;
  mtime: number;
  thumbnail_url: string;
  content_url: string;
};

export type UploadAsset = { uri: string; name: string; type: string };
export type UploadedImage = { id: string; filename: string; mime_type: string; size: number; width: number; height: number };
export type ImageWorkflowId = Extract<WorkflowId, "qwen_edit_2511" | "qwen_image_2_1_8gb_edit" | "qwen_image_2_1_8gb_t2i">;
export type ImageJobInput = {
  prompt: string;
  workflow: ImageWorkflowId;
  referenceAssetIds: string[];
  editSizeMode?: "scale" | "dimensions";
  scaleFactor?: number;
  width?: number;
  height?: number;
};

type JsonValue = unknown;

export class RemoteApi {
  private readonly root: string;

  constructor(baseUrl: string, public readonly token?: string) {
    this.root = baseUrl.replace(/\/+$/, "");
  }

  async pair(code: string, name: string): Promise<{ token: string }> {
    return this.request("/api/v1/pair", { method: "POST", body: { code, name }, authenticated: false });
  }

  async health(): Promise<Record<string, unknown>> {
    return this.request("/api/v1/health", { authenticated: false });
  }

  async uploadImages(files: UploadAsset[]): Promise<{ assets: UploadedImage[] }> {
    const form = new FormData();
    files.forEach((file) => form.append("files", file as unknown as Blob));
    return this.request("/api/v1/uploads/images", { method: "POST", body: form });
  }

  async importLibraryImage(image: LibraryImage): Promise<UploadedImage> {
    return this.request(`/api/v1/library-images/${encodeURIComponent(image.id)}/import`, { method: "POST" });
  }

  async createImageJob(input: ImageJobInput): Promise<GenerationJob> {
    return this.request("/api/v1/jobs/image", {
      method: "POST",
      body: input,
    });
  }

  async createVideoJob(prompt: string, referenceAssetIds: string[], width: number, height: number, frames: number): Promise<GenerationJob> {
    return this.request("/api/v1/jobs/video", {
      method: "POST",
      body: { prompt, referenceAssetIds, width, height, frames },
    });
  }

  async listJobs(): Promise<{ jobs: GenerationJob[] }> {
    return this.request("/api/v1/jobs");
  }

  async getJob(id: string): Promise<GenerationJob> {
    return this.request(`/api/v1/jobs/${encodeURIComponent(id)}`);
  }

  async cancelJob(id: string): Promise<GenerationJob> {
    return this.request(`/api/v1/jobs/${encodeURIComponent(id)}/cancel`, { method: "POST" });
  }

  async listArtifacts(): Promise<{ artifacts: Artifact[] }> {
    return this.request("/api/v1/artifacts");
  }

  async deleteArtifact(id: string): Promise<void> {
    await this.request(`/api/v1/artifacts/${encodeURIComponent(id)}`, { method: "DELETE" });
  }

  async listLibraries(): Promise<{ libraries: Library[] }> {
    return this.request("/api/v1/libraries");
  }

  async listLibraryImages(libraryId: string, offset = 0, limit = 50): Promise<{ images: LibraryImage[] }> {
    return this.request(`/api/v1/libraries/${encodeURIComponent(libraryId)}/images?offset=${offset}&limit=${limit}`);
  }

  mediaUrl(path: string): string {
    return /^https?:\/\//i.test(path) ? path : `${this.root}/${path.replace(/^\/+/, "")}`;
  }

  private async request<T extends JsonValue>(path: string, options: {
    method?: string;
    body?: unknown;
    authenticated?: boolean;
  } = {}): Promise<T> {
    const headers: Record<string, string> = this.authHeaders();
    const authenticated = options.authenticated !== false;
    if (authenticated && this.token) headers.Authorization = `Bearer ${this.token}`;
    const init: RequestInit = { method: options.method ?? "GET", headers };
    if (options.body instanceof FormData) {
      init.body = options.body;
    } else if (options.body !== undefined) {
      headers["Content-Type"] = "application/json";
      init.body = JSON.stringify(options.body);
    }
    const response = await fetch(this.mediaUrl(path), init);
    const raw = await response.text();
    let payload: unknown = {};
    try {
      payload = raw ? JSON.parse(raw) : {};
    } catch {
      payload = { detail: raw };
    }
    if (!response.ok) {
      const detail = typeof payload === "object" && payload && "detail" in payload ? String(payload.detail) : `HTTP ${response.status}`;
      throw new Error(detail);
    }
    return payload as T;
  }

  private authHeaders(): Record<string, string> {
    return this.token ? { Authorization: `Bearer ${this.token}` } : {};
  }
}
