import type { Theme } from "@/bridge";

// Light by default. Python opens the window as `#theme=dark` or `#theme=system` (a fragment:
// .NET escapes a file URL's "?"), so the page has its theme before its first paint; Settings
// switches it while the app runs.
export function initialTheme(hash: string = window.location.hash): Theme {
  const theme = new URLSearchParams(hash.replace(/^#/, "")).get("theme");
  return theme === "dark" || theme === "system" ? theme : "light";
}

let stopFollowing: (() => void) | null = null;

// Match Windows ("system") follows Windows' app mode live, as WebView2 reports it through
// `prefers-color-scheme`; choosing Light or Dark stops following.
export function applyTheme(theme: Theme, root: HTMLElement = document.documentElement): void {
  stopFollowing?.();
  stopFollowing = null;
  if (theme !== "system" || typeof window.matchMedia !== "function") {
    root.classList.toggle("dark", theme === "dark");
    return;
  }
  const windowsMode = window.matchMedia("(prefers-color-scheme: dark)");
  const follow = () => root.classList.toggle("dark", windowsMode.matches);
  follow();
  windowsMode.addEventListener("change", follow);
  stopFollowing = () => windowsMode.removeEventListener("change", follow);
}
