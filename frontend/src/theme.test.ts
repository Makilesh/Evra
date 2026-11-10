import { afterEach, expect, it, vi } from "vitest";
import { applyTheme, initialTheme } from "@/theme";

type Listener = (event: { matches: boolean }) => void;

// A stand-in for Windows' light/dark app mode, as WebView2 reports it to the page.
function fakeWindowsMode(dark: boolean) {
  const listeners = new Set<Listener>();
  const query = {
    matches: dark,
    addEventListener: (_: string, listener: Listener) => listeners.add(listener),
    removeEventListener: (_: string, listener: Listener) => listeners.delete(listener),
  };
  vi.stubGlobal("matchMedia", vi.fn(() => query));
  return {
    listeners,
    flip(next: boolean) {
      query.matches = next;
      listeners.forEach((listener) => listener({ matches: next }));
    },
  };
}

afterEach(() => vi.unstubAllGlobals());

it("opens light unless the window asks for dark or Match Windows", () => {
  expect(initialTheme("")).toBe("light");
  expect(initialTheme("#theme=dark")).toBe("dark");
  expect(initialTheme("#theme=system")).toBe("system");
  expect(initialTheme("#theme=sepia")).toBe("light");
});

it("switches the dark class", () => {
  const root = document.createElement("div");
  applyTheme("dark", root);
  expect(root.classList.contains("dark")).toBe(true);
  applyTheme("light", root);
  expect(root.classList.contains("dark")).toBe(false);
});

it("follows Windows while Match Windows is chosen, and stops after", () => {
  const windows = fakeWindowsMode(true);
  const root = document.createElement("div");
  applyTheme("system", root);
  expect(root.classList.contains("dark")).toBe(true);
  windows.flip(false);
  expect(root.classList.contains("dark")).toBe(false);
  applyTheme("light", root);
  windows.flip(true);
  expect(root.classList.contains("dark")).toBe(false);
  expect(windows.listeners.size).toBe(0);
});
