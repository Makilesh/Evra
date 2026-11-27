import { describe, expect, it } from "vitest";
import type { Note, Utterance } from "@/bridge";
import { noteQuotes, noteToMarkdown, pointCount } from "@/note";
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

describe("noteToMarkdown with items", () => {
  it("copies done items as checked", () => {
    const note: Note = {
      model: "m",
      sections: [
        {
          id: "action_items",
          title: "Action items",
          blocks: [
            {
              text: "You: Send the proposal (by Thursday)",
              citations: [{ utterance_id: "u2", start_ms: 110_000 }],
              item: { id: "i1", kind: "action_item", status: "done", owner: "You", due: "by Thursday" },
            },
            {
              text: "Them: Tell marketing",
              citations: [],
              item: { id: "i2", kind: "action_item", status: "open", owner: "Them", due: null },
            },
          ],
        },
        {
          id: "decisions",
          title: "Decisions",
          blocks: [
            {
              text: "Launch on October 14.",
              citations: [{ utterance_id: "u1", start_ms: 65_000 }],
              item: { id: "d1", kind: "decision", status: "open", owner: null, due: null },
            },
          ],
        },
      ],
    };
    expect(noteToMarkdown("Weekly 1:1", "Mon 28 Sept · 13:51 · 12 min", note)).toBe(
      [
        "# Weekly 1:1",
        "Mon 28 Sept · 13:51 · 12 min",
        "",
        "## Action items",
        "- [x] You: Send the proposal (by Thursday) (01:50)",
        "- [ ] Them: Tell marketing",
        "",
        "## Decisions",
        "- Launch on October 14. (01:05)",
        "",
      ].join("\n"),
    );
  });
});
