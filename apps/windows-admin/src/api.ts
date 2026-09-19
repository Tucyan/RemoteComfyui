export type Library = {
  id: string;
  name: string;
  path: string;
  recursive: boolean;
  enabled: boolean;
};

export type Health = {
  gateway?: { status?: string };
  comfyui?: { status?: string; version?: string | null; error?: string | null };
};

let csrfToken: string | null = null;

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function request<T>(url: string, init: RequestInit = {}, mutation = false): Promise<T> {
  if (mutation && !csrfToken) await getSession();
  const sourceHeaders = new Headers(init.headers);
  const headers: Record<string, string> = Object.fromEntries(sourceHeaders.entries());
  if (init.body && !sourceHeaders.has("content-type")) headers["content-type"] = "application/json";
  if (mutation && csrfToken) headers["x-csrf-token"] = csrfToken;
  let response: Response;
  try {
    response = await fetch(url, { ...init, headers, credentials: "same-origin" });
  } catch {
    throw new ApiError("无法连接 Gateway，请确认服务正在运行。", 0);
  }
  if (!response.ok) {
    let detail = "请求失败，请稍后重试。";
    try {
      const body = await response.json() as { detail?: string };
      if (body.detail) detail = body.detail;
    } catch {
      // The status message is enough when the response is not JSON.
    }
    throw new ApiError(detail, response.status);
  }
  if (response.status === 204) return undefined as T;
  return await response.json() as T;
}

export async function getSession(): Promise<string> {
  const result = await request<{ csrf_token: string }>("/admin/api/session");
  csrfToken = result.csrf_token;
  return csrfToken;
}

export function loadHealth() {
  return request<Health>("/api/v1/health");
}

export async function loadLibraries() {
  return (await request<{ libraries: Library[] }>("/admin/api/libraries")).libraries;
}

export async function loadDrives() {
  return (await request<{ drives: string[] }>("/admin/api/filesystem/drives")).drives;
}

export async function loadDirectories(path: string) {
  return (await request<{ directories: string[] }>(`/admin/api/filesystem/directories?path=${encodeURIComponent(path)}`)).directories;
}

export async function validatePath(path: string) {
  const result = await request<{ valid: boolean; path: string }>("/admin/api/filesystem/validate", { method: "POST", body: JSON.stringify({ path }) }, true);
  if (result.valid !== true || typeof result.path !== "string" || !result.path.trim()) throw new ApiError("目录验证失败，请检查路径。", 502);
  return result.path;
}

export function createLibrary(payload: Omit<Library, "id"> & { id?: string }) {
  return request<Library>("/admin/api/libraries", { method: "POST", body: JSON.stringify(payload) }, true);
}

export function updateLibrary(id: string, payload: Partial<Omit<Library, "id">>) {
  return request<Library>(`/admin/api/libraries/${encodeURIComponent(id)}`, { method: "PATCH", body: JSON.stringify(payload) }, true);
}

export function deleteLibrary(id: string) {
  return request<void>(`/admin/api/libraries/${encodeURIComponent(id)}`, { method: "DELETE" }, true);
}
