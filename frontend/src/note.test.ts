import { describe, expect, it } from "vitest";
import type { Note, Utterance } from "@/bridge";
import { noteQuotes, noteToMarkdown, pointCount, splitOwner } from "@/note";
import { DETAIL } from "@/test/fakeApi";

const BY_ID = new Map<string, Utterance>(DETAIL.utterances.map((u) => [u.id, u]));

describe("noteQuotes", () => {
  it("gives the cited lines in citation order", () => {
    const block = {
      text: "x",
      citations: [
        { utterance_id: "u2", start_ms: 110_000 },
        { utterance_id: "u1", start_ms: 65_000 },
      ],
    };
    expect(noteQuotes(block, BY_ID).map((u) => u.id)).toEqual(["u2", "u1"]);
  });

  it("skips unknown and repeated lines", () => {
    const block = {
      text: "x",
      citations: [
        { utterance_id: "gone", start_ms: 1_000 },
        { utterance_id: "u1", start_ms: 65_000 },
        { utterance_id: "u1", start_ms: 65_000 },
      ],
    };
    expect(noteQuotes(block, BY_ID).map((u) => u.id)).toEqual(["u1"]);
  });
});

describe("pointCount", () => {
  it("counts the points in every section", () => {
    expect(pointCount(DETAIL.note!)).toBe(2);
  });
});

describe("noteToMarkdown", () => {
  it("gives the title, the meeting line and each section with its times", () => {
    const note: Note = {
      model: "m",
      sections: [
        ...DETAIL.note!.sections,
        { id: "open_questions", title: "Open questions", blocks: [] },
      ],
    };
    expect(noteToMarkdown("Weekly 1:1", "Mon 28 Sept · 13:51 · 12 min", note)).toBe(
      [
        "# Weekly 1:1",
        "Mon 28 Sept · 13:51 · 12 min",
        "",
        "## Summary",
        "- Launch moves to October 14. (01:05)",
        "",
        "## Action items",
        "- You: send the proposal by Thursday. (01:50)",
        "",
      ].join("\n"),
    );
  });
});

describe("splitOwner", () => {
  it("separates a one-word owner from the rest of the point", () => {
    expect(splitOwner("You: send the proposal by Thursday.")).toEqual({
      owner: "You",
      rest: "send the proposal by Thursday.",
    });
    expect(splitOwner("Launch moves to October 14.")).toEqual({ owner: null, rest: "Launch moves to October 14." });
    expect(splitOwner("Note at 10:30 tomorrow.")).toEqual({ owner: null, rest: "Note at 10:30 tomorrow." });
  });
});
