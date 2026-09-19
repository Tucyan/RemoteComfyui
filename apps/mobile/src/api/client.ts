export type GenerationJob = {
  id: string;
  kind: "image" | "video";
  status: string;
  prompt_id?: string | null;
  error?: string | null;
  created_at?: number;
  updated_at?: number;
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

  async uploadImages(files: UploadAsset[]): Promise<{ assets: Array<{ id: string; filename: string; mime_type: string; size: number }> }> {
    const form = new FormData();
    files.forEach((file) => form.append("files", file as unknown as Blob));
    return this.request("/api/v1/uploads/images", { method: "POST", body: form });
  }

  async importLibraryImage(image: LibraryImage): Promise<{ id: string; filename: string; mime_type: string; size: number }> {
    const response = await fetch(this.mediaUrl(image.content_url), { headers: this.authHeaders() });
    if (!response.ok) throw new Error(`读取图库图片失败（HTTP ${response.status}）`);
    const blob = await response.blob();
    const form = new FormData();
    form.append("files", blob, image.name);
    const result = await this.request<{ assets: Array<{ id: string; filename: string; mime_type: string; size: number }> }>("/api/v1/uploads/images", { method: "POST", body: form });
    const uploaded = result.assets[0];
    if (!uploaded) throw new Error("图库图片上传失败");
    return uploaded;
  }

  async createImageJob(prompt: string, referenceAssetIds: string[]): Promise<GenerationJob> {
    return this.request("/api/v1/jobs/image", {
      method: "POST",
      body: { prompt, referenceAssetIds },
    });
  }

  async createVideoJob(prompt: string, referenceAssetIds: string[], resolutionPreset: string, frames: number): Promise<GenerationJob> {
    return this.request("/api/v1/jobs/video", {
      method: "POST",
      body: { prompt, referenceAssetIds, resolutionPreset, frames },
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
