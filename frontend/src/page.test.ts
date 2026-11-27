/// <reference types="node" />
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { expect, it } from "vitest";

// jsdom loads no CSS (and vitest blanks CSS imports), so the rules that keep the window from
// scrolling as a whole are pinned as text, read from disk. html and body never scroll; #root
// holds and clips every sr-only (absolute) element that no closer ancestor positions, so a
// time-tab jump (scrollIntoView) has no page to move.
const css = readFileSync(join(__dirname, "index.css"), "utf8");

it("never lets the window scroll as a whole", () => {
  expect(css).toMatch(/html,\s*body\s*\{\s*overflow:\s*hidden;\s*\}/);
  expect(css).toMatch(/#root\s*\{\s*position:\s*relative;\s*overflow:\s*clip;\s*\}/);
});
