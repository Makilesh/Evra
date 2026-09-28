import { expect, it } from "vitest";
import { applyTheme } from "@/theme";

it("toggles the dark class", () => {
  const root = document.createElement("div");
  applyTheme(true, root);
  expect(root.classList.contains("dark")).toBe(true);
  applyTheme(false, root);
  expect(root.classList.contains("dark")).toBe(false);
});
