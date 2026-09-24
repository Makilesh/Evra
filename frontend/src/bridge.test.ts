import { afterEach, describe, expect, it, vi } from "vitest";
import { emit, getApi, onEvent, setApiForTests, type EvraApi } from "@/bridge";

const fakeApi: EvraApi = {
  ping: async (m) => ({ reply: `pong: ${m}` }),
  app_info: async () => ({ name: "Evra", version: "0.1.0" }),
  request_hello: async () => null,
};

afterEach(() => {
  setApiForTests(null);
  delete window.pywebview;
});

describe("getApi", () => {
  it("returns the test override immediately", async () => {
    setApiForTests(fakeApi);
    await expect(getApi()).resolves.toBe(fakeApi);
  });

  it("waits for pywebviewready", async () => {
    const pending = getApi(1000);
    window.pywebview = { api: fakeApi };
    window.dispatchEvent(new Event("pywebviewready"));
    await expect(pending).resolves.toBe(fakeApi);
  });

  it("waits when pywebview has only injected an empty api object", async () => {
    window.pywebview = { api: {} as EvraApi };
    const pending = getApi(1000);
    window.pywebview = { api: fakeApi };
    window.dispatchEvent(new Event("pywebviewready"));
    await expect(pending).resolves.toBe(fakeApi);
  });

  it("rejects if pywebviewready fires but the api is still empty", async () => {
    window.pywebview = { api: {} as EvraApi };
    const pending = getApi(1000);
    window.dispatchEvent(new Event("pywebviewready"));
    await expect(pending).rejects.toThrow("pywebviewready fired without an api");
  });

  it("rejects when the bridge never appears", async () => {
    await expect(getApi(10)).rejects.toThrow("Python bridge not available");
  });
});

describe("events", () => {
  it("delivers emitted payloads and supports unsubscribe", () => {
    const handler = vi.fn();
    const off = onEvent("app.hello", handler);
    emit("app.hello", { n: 1 });
    off();
    emit("app.hello", { n: 2 });
    expect(handler).toHaveBeenCalledTimes(1);
    expect(handler).toHaveBeenCalledWith({ n: 1 });
  });

  it("is reachable from Python via window.__evraEmit", () => {
    const handler = vi.fn();
    const off = onEvent("x.y", handler);
    window.__evraEmit?.("x.y", "ok");
    off();
    expect(handler).toHaveBeenCalledWith("ok");
  });
});
