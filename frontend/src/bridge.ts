// Python <-> React bridge (BUILD.md §4, D5).
// JS -> Python: window.pywebview.api.<method>(...) returns a Promise.
// Python -> JS: Python runs window.__evraEmit(name, payload).

export interface AppInfo {
  name: string;
  version: string;
}

export interface PingReply {
  reply: string;
}

export interface EvraApi {
  ping(message: string): Promise<PingReply>;
  app_info(): Promise<AppInfo>;
  request_hello(): Promise<null>;
}

type Handler = (payload: unknown) => void;

declare global {
  interface Window {
    pywebview?: { api: EvraApi };
    __evraEmit?: (name: string, payload: unknown) => void;
  }
}

const handlers = new Map<string, Set<Handler>>();
let apiOverride: EvraApi | null = null;

export function setApiForTests(api: EvraApi | null): void {
  apiOverride = api;
}

// pywebview injects `window.pywebview = { api: {} }` first and fills in the methods later
// (then fires `pywebviewready`), so an api object alone does not mean it is usable.
function readyApi(): EvraApi | null {
  const api = window.pywebview?.api;
  return api && typeof api.app_info === "function" ? api : null;
}

export function getApi(timeoutMs = 10_000): Promise<EvraApi> {
  if (apiOverride) return Promise.resolve(apiOverride);
  const ready = readyApi();
  if (ready) return Promise.resolve(ready);
  return new Promise((resolve, reject) => {
    const onReady = () => {
      window.clearTimeout(timer);
      const api = readyApi();
      if (api) resolve(api);
      else reject(new Error("pywebviewready fired without an api"));
    };
    const timer = window.setTimeout(() => {
      window.removeEventListener("pywebviewready", onReady);
      reject(new Error("Python bridge not available"));
    }, timeoutMs);
    window.addEventListener("pywebviewready", onReady, { once: true });
  });
}

export function onEvent(name: string, handler: Handler): () => void {
  const set = handlers.get(name) ?? new Set<Handler>();
  handlers.set(name, set);
  set.add(handler);
  return () => {
    set.delete(handler);
  };
}

export function emit(name: string, payload: unknown): void {
  handlers.get(name)?.forEach((handler) => handler(payload));
}

window.__evraEmit = emit;
