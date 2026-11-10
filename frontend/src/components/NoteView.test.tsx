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
    ...extra,
  };
  render(<NoteView {...props} />);
  return props;
}

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

it("sets an action item's owner in bold", () => {
  sheet();
  expect(screen.getByText("You:").tagName).toBe("B");
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

it("explains a failure and offers Retry only when it can help", async () => {
  const onWrite = vi.fn();
  const { rerender } = render(
    <NoteView note={null} utterances={[]} status={{ failed: { reason: "invalid" } }} canWrite onWrite={onWrite} onCite={vi.fn()} />,
  );
  expect(screen.getByRole("alert")).toHaveTextContent("The model didn't return a valid note.");
  await userEvent.click(screen.getByRole("button", { name: "Retry" }));
  expect(onWrite).toHaveBeenCalled();
  rerender(
    <NoteView note={null} utterances={[]} status={{ failed: { reason: "too_long" } }} canWrite onWrite={onWrite} onCite={vi.fn()} />,
  );
  expect(screen.queryByRole("button", { name: "Retry" })).toBeNull();
});

it("offers to write a note for a meeting that has none", async () => {
  const props = sheet({ note: null });
  await userEvent.click(screen.getByRole("button", { name: "Write note" }));
  expect(props.onWrite).toHaveBeenCalled();
});
