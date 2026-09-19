import { beforeEach, describe, expect, it, vi } from "vitest";

const values = new Map<string, string>();
vi.mock("expo-secure-store", () => ({
  getItemAsync: vi.fn(async (key: string) => values.get(key) ?? null),
  setItemAsync: vi.fn(async (key: string, value: string) => void values.set(key, value)),
  deleteItemAsync: vi.fn(async (key: string) => void values.delete(key)),
}));

import { PairingStore } from "../src/storage/pairing";

describe("pairing persistence", () => {
  beforeEach(() => values.clear());

  it("restores and clears gateway pairing details", async () => {
    const store = new PairingStore();
    await store.save({ baseUrl: "http://192.168.1.20:3000", token: "rc_token", deviceName: "phone" });
    await expect(store.load()).resolves.toEqual({
      baseUrl: "http://192.168.1.20:3000",
      token: "rc_token",
      deviceName: "phone",
    });
    await store.clear();
    await expect(store.load()).resolves.toBeNull();
  });
});
