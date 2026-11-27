import { describe, expect, it } from "vitest";
import type { NoteLine } from "@/bridge";
import { MAX_LINE_CHARS, lineAt, padLines, splitText, typedAt, withText } from "@/notepad";
import { DETAIL, MEETING } from "@/test/fakeApi";

const line = (id: string, text: string, captured_at: number | null = null): NoteLine => ({
  id,
  text,
  captured_at,
  pasted: false,
});

describe("withText", () => {
  it("stamps a line the first time it gets more than spaces, and keeps that time", () => {
    const blank = withText(line("a", ""), "   ", 1_000);
    expect(blank.captured_at).toBeNull();
    const typed = withText(blank, "Budget", 2_000);
    expect(typed.captured_at).toBe(2_000);
    expect(withText(withText(typed, "", 3_000), "Again", 4_000).captured_at).toBe(2_000);
  });
});

describe("typedAt", () => {
  it("gives a line's time in the call, and none for a line typed after it", () => {
    expect(typedAt(line("a", "x", MEETING.started_at + 110_000), MEETING)).toBe(110_000);
    expect(typedAt(line("a", "x", MEETING.started_at + 720_000), MEETING)).toBeNull(); // the end
    expect(typedAt(line("a", "x", MEETING.started_at - 1), MEETING)).toBeNull();
    expect(typedAt(line("a", "x"), MEETING)).toBeNull();
    const live = { ...MEETING, duration_ms: null };
    expect(typedAt(line("a", "x", MEETING.started_at + 5_000_000), live)).toBe(5_000_000);
  });
});

describe("lineAt", () => {
  it("finds the line being said at a time: the last one started by then, else the first", () => {
    expect(lineAt(DETAIL.utterances, 112_000)?.id).toBe("u2");
    expect(lineAt(DETAIL.utterances, 100_000)?.id).toBe("u1");
    expect(lineAt(DETAIL.utterances, 1_000)?.id).toBe("u1");
    expect(lineAt([], 1_000)).toBeUndefined();
  });
});

describe("padLines", () => {
  it("keeps the window's own lines and takes the links Python found since", () => {
    const stored = [{ ...line("a", "old text"), aligned: [{ utterance_id: "u1", start_ms: 65_000 }] }];
    expect(padLines(undefined, stored)).toBe(stored);
    const local = [line("a", "new text"), line("b", "not saved yet")];
    expect(padLines(local, stored)).toEqual([
      { ...line("a", "new text"), aligned: [{ utterance_id: "u1", start_ms: 65_000 }] },
      line("b", "not saved yet"),
    ]);
  });
});

describe("splitText", () => {
  it("leaves a text that fits as it is", () => {
    expect(splitText("a short note")).toEqual(["a short note"]);
    expect(splitText("x".repeat(MAX_LINE_CHARS))).toEqual(["x".repeat(MAX_LINE_CHARS)]);
  });

  it("cuts at the last line break that fits, else the last space, else at the limit", () => {
    expect(splitText("one two\nthree four\nfive", 12)).toEqual(["one two", "three four", "five"]);
    expect(splitText("one two three four", 9)).toEqual(["one two", "three", "four"]);
    expect(splitText("abcdefghij", 4)).toEqual(["abcd", "efgh", "ij"]);
  });

  it("never splits a character in two or leaves an empty piece", () => {
    expect(splitText("abc\u{1F600}def", 4)).toEqual(["abc", "\u{1F600}de", "f"]);
    expect(splitText("ab\n\n\ncd", 3)).toEqual(["ab", "cd"]);
  });
});
