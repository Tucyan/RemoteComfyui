import { afterEach, describe, expect, it, vi } from "vitest";
import { validatePath } from "../src/api";

describe("path validation response", () => {
  afterEach(() => vi.restoreAllMocks());

  it("rejects a 200 response that does not confirm a valid path", async () => {
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      if (String(input).endsWith("/admin/api/session")) return new Response(JSON.stringify({ csrf_token: "csrf" }), { status: 200 });
      return new Response(JSON.stringify({ valid: false, path: "C:\\Missing" }), { status: 200 });
    }));
    await expect(validatePath("C:\\Missing")).rejects.toThrow("目录验证失败");
  });
});
