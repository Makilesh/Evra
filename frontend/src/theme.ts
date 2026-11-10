import type { Theme } from "@/bridge";

// Light by default. Python opens a dark window as `#theme=dark` (a fragment: .NET escapes a
// file URL's "?"), so the page is dark before its first paint; Settings switches it while the
// app runs.
export function initialTheme(hash: string = window.location.hash): Theme {
  return new URLSearchParams(hash.replace(/^#/, "")).get("theme") === "dark" ? "dark" : "light";
}

export function applyTheme(theme: Theme, root: HTMLElement = document.documentElement): void {
  root.classList.toggle("dark", theme === "dark");
}
