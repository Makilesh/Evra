import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import type { Note } from "@/bridge";
import { NoteView } from "@/components/NoteView";
import { DETAIL } from "@/test/fakeApi";

function sheet(extra: Partial<Parameters<typeof NoteView>[0]> = {}) {
  const props = {
    note: DETAIL.note,
    utterances: DETAIL.utterances,
    status: undefined,
    canWrite: true,
    onWrite: vi.fn(),
    onCite: vi.fn(),
    onItemStatus: vi.fn(),
    ...extra,
  };
  const { rerender } = render(<NoteView {...props} />);
  return { ...props, rerender };
}

function withItems(status: "open" | "done"): Note {
  return {
    model: "gemma4:12b",
    sections: [
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
      {
        id: "action_items",
        title: "Action items",
        blocks: [
          {
            text: "You: Send the proposal (by Thursday)",
            citations: [{ utterance_id: "u2", start_ms: 110_000 }],
            item: { id: "i1", kind: "action_item", status, owner: "You", due: "by Thursday" },
          },
        ],
      },
    ],
  };
}

it("ticks an action item done", async () => {
  const { rerender, ...props } = sheet({ note: withItems("open") });
  const box = screen.getByRole("checkbox", { name: "Done: You: Send the proposal (by Thursday)" });
  expect(box).not.toBeChecked();
  expect(screen.getAllByRole("checkbox")).toHaveLength(1); // a decision is not ticked off
  await userEvent.click(box);
  expect(props.onItemStatus).toHaveBeenCalledWith("i1", "done");

  rerender(<NoteView {...props} note={withItems("done")} />);
  const ticked = screen.getByRole("checkbox", { name: "Done: You: Send the proposal (by Thursday)" });
  expect(ticked).toBeChecked();
  const row = ticked.closest("li")!;
  expect(within(row).getByText(/Send the proposal/)).toHaveClass("line-through", "text-muted");
  expect(within(row).getByText("You:").tagName).toBe("B");
  await userEvent.click(ticked);
  expect(props.onItemStatus).toHaveBeenLastCalledWith("i1", "open");
});

it("keeps the Done box's hidden checkbox inside its row", () => {
  sheet({ note: withItems("open") });
  const box = screen.getByRole("checkbox", { name: "Done: You: Send the proposal (by Thursday)" });
  expect(box).toHaveClass("sr-only");
  // sr-only is position: absolute; a positioned label keeps it in the note's scroller, so a tick
  // or Tab scrolls only to the row, never the whole window (jsdom loads no CSS: the class pins it)
  expect(box.closest("label")).toHaveClass("relative");
});

it("shows sections with time tabs that jump to the transcript", async () => {
  const props = sheet();
  expect(screen.getByRole("heading", { name: "Action items" })).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Jump to 01:50 in the transcript" }));
  expect(props.onCite).toHaveBeenCalledWith("u2");
});

it("puts each point beside the lines it came from", () => {
  sheet();
  const row = screen.getByText("Launch moves to October 14.").closest("li")!;
  expect(within(row).getByRole("button", { name: "Jump to 01:05 in the transcript" })).toBeInTheDocument();
  expect(row).toHaveTextContent("Them");
  expect(within(row).getByText("Marketing wants October 14.").tagName).toBe("Q");
});

it("sets an action item's owner in bold, as its record names it", () => {
  const note = withItems("open");
  note.sections[1].blocks.push({
    text: "Finance: send the budget", // nobody owns it: the word before the colon is no owner
    citations: [],
    item: { id: "i2", kind: "action_item", status: "open", owner: null, due: null },
  });
  sheet({ note });
  expect(screen.getByText("You:").tagName).toBe("B");
  expect(screen.getByText("Finance: send the budget")).toBeInTheDocument();
  expect(screen.queryByText("Finance:")).toBeNull();
});

it("quotes the owner's own line beside a point from their notes", () => {
  const note: Note = {
    model: "m",
    sections: [
      {
        id: "summary",
        title: "Summary",
        blocks: [
          {
            text: "The designer budget was approved.",
            citations: [{ utterance_id: "u1", start_ms: 65_000 }],
            user_quote: { id: "a", text: "designer budget ok" },
          },
        ],
      },
    ],
  };
  sheet({ note });
  const row = screen.getByText("The designer budget was approved.").closest("li")!;
  const quotes = within(row).getAllByText(/./, { selector: "q" });
  expect(quotes.map((q) => q.textContent)).toEqual(["Marketing wants October 14.", "designer budget ok"]);
  expect(quotes[1].closest("p")).toHaveTextContent(/^From your notes/);
});

it("shows a point whose cited line is gone", () => {
  const note: Note = {
    model: "m",
    sections: [
      { id: "summary", title: "Summary", blocks: [{ text: "Still here.", citations: [{ utterance_id: "gone", start_ms: 5_000 }] }] },
    ],
  };
  sheet({ note });
  const row = screen.getByText("Still here.").closest("li")!;
  expect(within(row).getByRole("button", { name: "Jump to 00:05 in the transcript" })).toBeInTheDocument();
  expect(row.querySelector("q")).toBeNull();
});

it("leaves out sections with no points", () => {
  sheet({ note: { ...DETAIL.note!, sections: [...DETAIL.note!.sections, { id: "next", title: "For next time", blocks: [] }] } });
  expect(screen.queryByRole("heading", { name: "For next time" })).toBeNull();
});

it("shows progress instead of an old note while a new one is written", () => {
  sheet({ status: { stage: "writing" }, canWrite: false });
  expect(screen.getByRole("status")).toHaveTextContent("Writing note…");
  expect(screen.queryByText("Launch moves to October 14.")).toBeNull();
});

it("says which part of a long call is being read", () => {
  sheet({ status: { stage: "part:2:6" }, canWrite: false });
  expect(screen.getByRole("status")).toHaveTextContent("Reading part 2 of 6…");
});

it("explains a failure and offers Retry only when it can help", async () => {
  const onWrite = vi.fn();
  const { rerender } = render(
    <NoteView note={null} utterances={[]} status={{ failed: { reason: "invalid" } }} canWrite onWrite={onWrite} onCite={vi.fn()} onItemStatus={vi.fn()} />,
  );
  expect(screen.getByRole("alert")).toHaveTextContent("The model didn't return a valid note.");
  await userEvent.click(screen.getByRole("button", { name: "Retry" }));
  expect(onWrite).toHaveBeenCalled();
  rerender(
    <NoteView note={null} utterances={[]} status={{ failed: { reason: "too_long" } }} canWrite onWrite={onWrite} onCite={vi.fn()} onItemStatus={vi.fn()} />,
  );
  expect(screen.queryByRole("button", { name: "Retry" })).toBeNull();
});

it("offers to write a note for a meeting that has none", async () => {
  const props = sheet({ note: null });
  await userEvent.click(screen.getByRole("button", { name: "Write note" }));
  expect(props.onWrite).toHaveBeenCalled();
});
