import * as SecureStore from "expo-secure-store";

export type PairingDetails = {
  baseUrl: string;
  token: string;
  deviceName: string;
};

const STORAGE_KEY = "remote-comfyui-pairing-v1";

export class PairingStore {
  async load(): Promise<PairingDetails | null> {
    const raw = await SecureStore.getItemAsync(STORAGE_KEY);
    if (!raw) return null;
    try {
      const parsed = JSON.parse(raw) as Partial<PairingDetails>;
      if (typeof parsed.baseUrl !== "string" || typeof parsed.token !== "string" || typeof parsed.deviceName !== "string") {
        return null;
      }
      return { baseUrl: parsed.baseUrl, token: parsed.token, deviceName: parsed.deviceName };
    } catch {
      return null;
    }
  }

  async save(details: PairingDetails): Promise<void> {
    await SecureStore.setItemAsync(STORAGE_KEY, JSON.stringify(details));
  }

  async clear(): Promise<void> {
    await SecureStore.deleteItemAsync(STORAGE_KEY);
  }
}
