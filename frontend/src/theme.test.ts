import { expect, it } from "vitest";
import { applyTheme, initialTheme } from "@/theme";

it("opens light unless the window asks for dark", () => {
  expect(initialTheme("")).toBe("light");
  expect(initialTheme("#theme=dark")).toBe("dark");
  expect(initialTheme("#theme=system")).toBe("light");
  expect(initialTheme("#x=1&theme=dark")).toBe("dark");
});

it("switches the dark class", () => {
  const root = document.createElement("div");
  applyTheme("dark", root);
  expect(root.classList.contains("dark")).toBe(true);
  applyTheme("light", root);
  expect(root.classList.contains("dark")).toBe(false);
});
