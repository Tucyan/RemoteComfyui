import "@testing-library/jest-dom/vitest";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AdminApp } from "../src/AdminApp";

const jsonResponse = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });

describe("AdminApp", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/admin/api/session")) return jsonResponse({ csrf_token: "csrf-123" });
      if (url.endsWith("/api/v1/health")) return jsonResponse({ gateway: { status: "online" }, comfyui: { status: "online", version: "0.3.0" } });
      if (url.endsWith("/admin/api/libraries") && (!init?.method || init.method === "GET")) return jsonResponse({ libraries: [] });
      if (url.endsWith("/admin/api/filesystem/drives")) return jsonResponse({ drives: ["C:\\"] });
      if (url.includes("/admin/api/filesystem/directories")) return jsonResponse({ directories: ["C:\\Pictures"] });
      if (url.endsWith("/admin/api/filesystem/validate")) return jsonResponse({ valid: true, path: "C:\\Pictures" });
      return jsonResponse({}, 404);
    }));
  });

  afterEach(() => vi.restoreAllMocks());

  it("loads overview and an empty libraries state", async () => {
    render(<AdminApp />);
    expect(await screen.findByRole("heading", { name: "状态概览" })).toBeInTheDocument();
    expect(await screen.findByText("还没有配置图片目录")).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("ComfyUI 在线");
  });

  it("shows a readable error when library loading fails", async () => {
    vi.mocked(fetch).mockImplementationOnce(async () => jsonResponse({ csrf_token: "csrf-123" }));
    vi.mocked(fetch).mockImplementationOnce(async () => jsonResponse({}, 503));
    render(<AdminApp />);
    expect(await screen.findByRole("alert")).toHaveTextContent("图片目录加载失败");
  });

  it("browses a drive directory and selects the validated path", async () => {
    render(<AdminApp />);
    await screen.findByText("还没有配置图片目录");
    await userEvent.click(screen.getByRole("button", { name: "新增目录" }));
    expect(await screen.findByRole("dialog", { name: "新增图片目录" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "C:\\" }));
    expect(await screen.findByRole("button", { name: "选择 C:\\Pictures" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "选择 C:\\Pictures" }));
    expect(screen.getByLabelText("目录路径")).toHaveValue("C:\\Pictures");
  });

  it("expands nested folders and selects a deep path", async () => {
    vi.mocked(fetch).mockImplementation(async (input, init) => {
      const url = String(input);
      if (url.endsWith("/admin/api/session")) return jsonResponse({ csrf_token: "csrf-123" });
      if (url.endsWith("/api/v1/health")) return jsonResponse({ gateway: { status: "online" }, comfyui: { status: "online" } });
      if (url.endsWith("/admin/api/libraries")) return jsonResponse({ libraries: [] });
      if (url.endsWith("/admin/api/filesystem/drives")) return jsonResponse({ drives: ["C:\\"] });
      if (url.includes("/admin/api/filesystem/directories")) {
        const path = new URL(url, "http://localhost").searchParams.get("path");
        return jsonResponse({ directories: path === "C:\\" ? ["C:\\Pictures"] : path === "C:\\Pictures" ? ["C:\\Pictures\\Trips"] : [] });
      }
      if (url.endsWith("/admin/api/filesystem/validate")) return jsonResponse({ valid: true, path: "C:\\Pictures\\Trips" });
      return jsonResponse({}, 404);
    });
    render(<AdminApp />);
    await screen.findByText("还没有配置图片目录");
    await userEvent.click(screen.getByRole("button", { name: "新增目录" }));
    await userEvent.click(screen.getByRole("button", { name: "C:\\" }));
    await userEvent.click(await screen.findByRole("button", { name: "展开 C:\\Pictures" }));
    await userEvent.click(await screen.findByRole("button", { name: "选择 C:\\Pictures\\Trips" }));
    expect(screen.getByLabelText("目录路径")).toHaveValue("C:\\Pictures\\Trips");
  });

  it("keeps a folder collapsed when its pending directory load finishes", async () => {
    let resolveDirectories!: (response: Response) => void;
    vi.mocked(fetch).mockImplementation(async (input) => {
      const url = String(input);
      if (url.endsWith("/admin/api/session")) return jsonResponse({ csrf_token: "csrf-123" });
      if (url.endsWith("/api/v1/health")) return jsonResponse({ gateway: { status: "online" }, comfyui: { status: "online" } });
      if (url.endsWith("/admin/api/libraries")) return jsonResponse({ libraries: [] });
      if (url.endsWith("/admin/api/filesystem/drives")) return jsonResponse({ drives: ["C:\\"] });
      if (url.includes("/admin/api/filesystem/directories")) return new Promise<Response>((resolve) => { resolveDirectories = resolve; });
      return jsonResponse({}, 404);
    });
    render(<AdminApp />);
    await screen.findByText("还没有配置图片目录");
    await userEvent.click(screen.getByRole("button", { name: "新增目录" }));
    const drive = await screen.findByRole("button", { name: "C:\\" });
    await userEvent.click(drive);
    expect(drive).toHaveAttribute("aria-expanded", "true");
    await userEvent.click(drive);
    resolveDirectories(jsonResponse({ directories: ["C:\\Pictures"] }));
    await waitFor(() => expect(drive).toHaveAttribute("aria-expanded", "false"));
    expect(screen.queryByRole("button", { name: "选择 C:\\Pictures" })).not.toBeInTheDocument();
  });

  it("preserves edits made while folder validation is pending", async () => {
    let resolveValidation!: (response: Response) => void;
    vi.mocked(fetch).mockImplementation(async (input) => {
      const url = String(input);
      if (url.endsWith("/admin/api/session")) return jsonResponse({ csrf_token: "csrf-123" });
      if (url.endsWith("/api/v1/health")) return jsonResponse({ gateway: { status: "online" }, comfyui: { status: "online" } });
      if (url.endsWith("/admin/api/libraries")) return jsonResponse({ libraries: [] });
      if (url.endsWith("/admin/api/filesystem/drives")) return jsonResponse({ drives: [] });
      if (url.endsWith("/admin/api/filesystem/validate")) return new Promise<Response>((resolve) => { resolveValidation = resolve; });
      return jsonResponse({}, 404);
    });
    render(<AdminApp />);
    await screen.findByText("还没有配置图片目录");
    await userEvent.click(screen.getByRole("button", { name: "新增目录" }));
    await userEvent.type(screen.getByLabelText("目录名称"), "之前");
    await userEvent.type(screen.getByLabelText("目录路径"), "C:\\Pictures");
    await userEvent.click(screen.getByRole("button", { name: "验证路径" }));
    await userEvent.clear(screen.getByLabelText("目录名称"));
    await userEvent.type(screen.getByLabelText("目录名称"), "之后");
    resolveValidation(jsonResponse({ valid: true, path: "C:\\Pictures" }));
    await screen.findByText("路径已验证");
    expect(screen.getByLabelText("目录名称")).toHaveValue("之后");
  });

  it("validates a manually entered path before saving and shows failures in the dialog", async () => {
    vi.mocked(fetch).mockImplementation(async (input, init) => {
      const url = String(input);
      if (url.endsWith("/admin/api/session")) return jsonResponse({ csrf_token: "csrf-123" });
      if (url.endsWith("/api/v1/health")) return jsonResponse({ gateway: { status: "online" }, comfyui: { status: "online" } });
      if (url.endsWith("/admin/api/libraries")) return jsonResponse({ libraries: [] });
      if (url.endsWith("/admin/api/filesystem/drives")) return jsonResponse({ drives: [] });
      if (url.endsWith("/admin/api/filesystem/validate")) return jsonResponse({ detail: "目录不存在" }, 400);
      return jsonResponse({}, 404);
    });
    render(<AdminApp />);
    await screen.findByText("还没有配置图片目录");
    await userEvent.click(screen.getByRole("button", { name: "新增目录" }));
    const dialog = screen.getByRole("dialog", { name: "新增图片目录" });
    await userEvent.type(within(dialog).getByLabelText("目录名称"), "测试目录");
    await userEvent.type(within(dialog).getByLabelText("目录路径"), "C:\\Missing");
    await userEvent.click(within(dialog).getByRole("button", { name: "验证路径" }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("目录不存在");
    await userEvent.click(within(dialog).getByRole("button", { name: "保存目录" }));
    await waitFor(() => expect(fetch).toHaveBeenCalledWith("/admin/api/filesystem/validate", expect.objectContaining({ method: "POST" })));
    expect(vi.mocked(fetch).mock.calls.some(([input, init]) => String(input).endsWith("/admin/api/libraries") && init?.method === "POST")).toBe(false);
  });

  it("edits name and canonical path with PATCH", async () => {
    const initial = { id: "photos", name: "旧名称", path: "C:\\Old", recursive: true, enabled: true };
    vi.mocked(fetch).mockImplementation(async (input, init) => {
      const url = String(input);
      if (url.endsWith("/admin/api/session")) return jsonResponse({ csrf_token: "csrf-123" });
      if (url.endsWith("/api/v1/health")) return jsonResponse({ gateway: { status: "online" }, comfyui: { status: "online" } });
      if (url.endsWith("/admin/api/libraries") && !init?.method) return jsonResponse({ libraries: [initial] });
      if (url.endsWith("/admin/api/filesystem/drives")) return jsonResponse({ drives: [] });
      if (url.endsWith("/admin/api/filesystem/validate")) return jsonResponse({ valid: true, path: "C:\\Canonical" });
      if (url.endsWith("/admin/api/libraries/photos") && init?.method === "PATCH") return jsonResponse({ ...initial, name: "新名称", path: "C:\\Canonical" });
      return jsonResponse({}, 404);
    });
    render(<AdminApp />);
    await screen.findByText("旧名称");
    await userEvent.click(screen.getByRole("button", { name: "编辑 旧名称" }));
    const dialog = screen.getByRole("dialog", { name: "编辑图片目录" });
    await userEvent.clear(within(dialog).getByLabelText("目录名称"));
    await userEvent.type(within(dialog).getByLabelText("目录名称"), "新名称");
    await userEvent.clear(within(dialog).getByLabelText("目录路径"));
    await userEvent.type(within(dialog).getByLabelText("目录路径"), "C:\\New");
    await userEvent.click(within(dialog).getByRole("button", { name: "保存目录" }));
    await waitFor(() => expect(fetch).toHaveBeenCalledWith("/admin/api/libraries/photos", expect.objectContaining({ method: "PATCH", body: JSON.stringify({ name: "新名称", path: "C:\\Canonical", recursive: true, enabled: true }) })));
  });

  it("creates a library with csrf, toggles it, and confirms delete configuration", async () => {
    let saved = false;
    let savedLibrary = { id: "pictures-2", name: "我的照片", path: "C:\\Pictures", recursive: true, enabled: true };
    vi.mocked(fetch).mockImplementation(async (input, init) => {
      const url = String(input);
      if (url.endsWith("/admin/api/session")) return jsonResponse({ csrf_token: "csrf-123" });
      if (url.endsWith("/api/v1/health")) return jsonResponse({ gateway: { status: "online" }, comfyui: { status: "offline" } });
      if (url.endsWith("/admin/api/filesystem/validate")) return jsonResponse({ valid: true, path: "C:\\Pictures" });
      if (url.endsWith("/admin/api/libraries") && init?.method === "POST") { saved = true; return jsonResponse(savedLibrary, 201); }
      if (url.includes("/admin/api/libraries/pictures-2") && init?.method === "PATCH") { savedLibrary = { ...savedLibrary, enabled: false }; return jsonResponse(savedLibrary); }
      if (url.includes("/admin/api/libraries/pictures-2") && init?.method === "DELETE") { saved = false; return new Response(null, { status: 204 }); }
      if (url.endsWith("/admin/api/libraries")) return jsonResponse({ libraries: saved ? [savedLibrary] : [] });
      return jsonResponse({ drives: [] });
    });
    render(<AdminApp />);
    await screen.findByText("还没有配置图片目录");
    await userEvent.click(screen.getByRole("button", { name: "新增目录" }));
    await userEvent.type(screen.getByLabelText("目录名称"), "我的照片");
    await userEvent.type(screen.getByLabelText("目录路径"), "C:\\Pictures");
    await userEvent.click(screen.getByRole("button", { name: "保存目录" }));
    await waitFor(() => expect(fetch).toHaveBeenCalledWith("/admin/api/libraries", expect.objectContaining({ method: "POST", headers: expect.objectContaining({ "x-csrf-token": "csrf-123" }) })));
    expect(await screen.findByText("我的照片")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "停用 我的照片" }));
    await waitFor(() => expect(fetch).toHaveBeenCalledWith("/admin/api/libraries/pictures-2", expect.objectContaining({ method: "PATCH", headers: expect.objectContaining({ "x-csrf-token": "csrf-123" }) })));
    await userEvent.click(screen.getByRole("button", { name: "删除 我的照片" }));
    expect(screen.getByRole("dialog", { name: "确认删除" })).toHaveTextContent("仅删除目录配置，不会删除原图");
    await userEvent.click(within(screen.getByRole("dialog", { name: "确认删除" })).getByRole("button", { name: "确认删除" }));
    await waitFor(() => expect(fetch).toHaveBeenCalledWith("/admin/api/libraries/pictures-2", expect.objectContaining({ method: "DELETE", headers: expect.objectContaining({ "x-csrf-token": "csrf-123" }) })));
  });
});
