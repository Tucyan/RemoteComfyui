import { describe, expect, it } from "vitest";
import config from "../vite.config";

describe("production asset base", () => {
  it("loads bundled assets under the admin route", () => {
    expect(config.base).toBe("/admin/");
  });
});
