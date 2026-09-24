export function applyTheme(dark: boolean, root: HTMLElement = document.documentElement): void {
  root.classList.toggle("dark", dark);
}

export function followSystemTheme(): () => void {
  const query = window.matchMedia("(prefers-color-scheme: dark)");
  applyTheme(query.matches);
  const onChange = (event: MediaQueryListEvent) => applyTheme(event.matches);
  query.addEventListener("change", onChange);
  return () => query.removeEventListener("change", onChange);
}
