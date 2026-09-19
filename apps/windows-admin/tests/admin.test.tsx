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
    expect(await screen.findByRole("button", { name: "C:\\Pictures" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "C:\\Pictures" }));
    expect(screen.getByLabelText("目录路径")).toHaveValue("C:\\Pictures");
  });

  it("creates a library with csrf, toggles it, and confirms delete configuration", async () => {
    let saved = false;
    let savedLibrary = { id: "pictures-2", name: "我的照片", path: "C:\\Pictures", recursive: true, enabled: true };
    vi.mocked(fetch).mockImplementation(async (input, init) => {
      const url = String(input);
      if (url.endsWith("/admin/api/session")) return jsonResponse({ csrf_token: "csrf-123" });
      if (url.endsWith("/api/v1/health")) return jsonResponse({ gateway: { status: "online" }, comfyui: { status: "offline" } });
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
