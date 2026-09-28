import { expect, it } from "vitest";
import { cn } from "@/lib/utils";

it("merges conflicting tailwind classes and drops falsy ones", () => {
  const isHidden: boolean = Math.random() > 2;
  expect(cn("px-2", "px-4", isHidden && "hidden")).toBe("px-4");
});
