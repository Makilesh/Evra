import { fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";
import type { NoteLine, Person, Question } from "@/bridge";
import { MeetingView } from "@/components/MeetingView";
import { DETAIL, MEETING } from "@/test/fakeApi";
import type { WithRefusal } from "@/usePeople";

const PRIYA: Person = { id: "p1", name: "Priya" };
const PEOPLE: Person[] = [PRIYA, { id: "p2", name: "Sam" }];

function view(extra: Partial<Parameters<typeof MeetingView>[0]> = {}) {
  const props = {
    detail: DETAIL,
    isLive: false,
    noteStatus: undefined,
    hints: undefined,
    canWrite: true,
    notes: [] as NoteLine[],
    notesFailed: false,
    onWrite: vi.fn(),
    onRename: vi.fn(async () => true),
    onAsk: vi.fn(async () => null),
    onPrepareAsk: vi.fn(),
    onItemStatus: vi.fn(),
    onNotes: vi.fn(),
    people: PEOPLE,
    onSetPerson: vi.fn(async (): Promise<WithRefusal | null> => null),
    ...extra,
  };
  return { props, ...render(<MeetingView {...props} />) };
}

function mockClipboard(writeText: (text: string) => Promise<void>) {
  Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText: vi.fn(writeText) } });
  return navigator.clipboard.writeText as ReturnType<typeof vi.fn>;
}

afterEach(() => {
  Reflect.deleteProperty(navigator, "clipboard");
});

it("opens a finished meeting on its note", () => {
  view();
  expect(screen.getByRole("tab", { name: "Note" })).toHaveAttribute("aria-selected", "true");
  screen.getByText("Launch moves to October 14.");
});

it("opens My notes while live", () => {
  const { rerender, props } = view({ isLive: true });
  expect(screen.getByRole("tab", { name: "My notes" })).toHaveAttribute("aria-selected", "true");
  expect(screen.getByRole("textbox", { name: "Note line 1" })).toHaveFocus();
  // after Stop, the note's progress: linking the typed lines comes first
  rerender(<MeetingView {...props} isLive={false} noteStatus={{ stage: "linking" }} />);
  expect(screen.getByRole("tab", { name: "Note" })).toHaveAttribute("aria-selected", "true");
  expect(screen.getByRole("status")).toHaveTextContent("Linking your notes…");
});

it("opens an empty pad on its line when My notes is clicked", async () => {
  view();
  await userEvent.click(screen.getByRole("tab", { name: "My notes" }));
  expect(screen.getByRole("textbox", { name: "Note line 1" })).toHaveFocus();
});

it("hands each change of the pad on, and the typed time opens the transcript there", async () => {
  const typed: NoteLine = { id: "a", text: "Proposal by Thursday", captured_at: MEETING.started_at + 112_000, pasted: false };
  const { props } = view({ notes: [typed] });
  await userEvent.click(screen.getByRole("tab", { name: "My notes" }));
  await userEvent.type(screen.getByRole("textbox", { name: "Note line 1" }), "!");
  expect(props.onNotes).toHaveBeenLastCalledWith([{ ...typed, text: "Proposal by Thursday!" }]);
  await userEvent.click(screen.getByRole("button", { name: "Jump to 01:52 in the transcript" }));
  expect(screen.getByRole("tab", { name: "Transcript" })).toHaveAttribute("aria-selected", "true");
  // the line being said when it was typed (01:50)
  expect(screen.getByText("I'll send the proposal by Thursday.").closest("li")).toHaveAttribute("data-highlighted", "true");
});

it("says when the notes couldn't be saved, whichever tab is open", () => {
  view({ notesFailed: true });
  expect(screen.getByRole("alert")).toHaveTextContent(
    "Couldn't save your notes. They stay here; Evra tries again as you type.",
  );
});

it("keeps the tab the owner chose while the note moves on to its next stage", async () => {
  const { rerender, props } = view({ noteStatus: { stage: "writing" } });
  await userEvent.click(screen.getByRole("tab", { name: "Transcript" }));
  rerender(<MeetingView {...props} noteStatus={{ stage: "items" }} />);
  expect(screen.getByRole("tab", { name: "Transcript" })).toHaveAttribute("aria-selected", "true");
});

it("jumps from a citation to its highlighted transcript line", async () => {
  view();
  await userEvent.click(screen.getByRole("button", { name: "Jump to 01:05 in the transcript" }));
  expect(screen.getByRole("tab", { name: "Transcript" })).toHaveAttribute("aria-selected", "true");
  expect(screen.getByText("Marketing wants October 14.").closest("li")).toHaveAttribute("data-highlighted", "true");
});

it("renames the meeting in place", async () => {
  const { props } = view();
  await userEvent.click(screen.getByRole("button", { name: "Rename meeting" }));
  const input = screen.getByRole("textbox", { name: "Meeting title" });
  await userEvent.clear(input);
  await userEvent.type(input, "Sync with Priya{Enter}");
  expect(props.onRename).toHaveBeenCalledWith("Sync with Priya");
  expect(screen.queryByRole("textbox", { name: "Meeting title" })).toBeNull();
});

it("shows the capture notes from the recording", () => {
  view({ hints: ["No system audio arrived."] });
  expect(screen.getByRole("list", { name: "Capture notes" })).toHaveTextContent("No system audio arrived.");
});

it("shows the title, then the day, time, length and kind of meeting", () => {
  view();
  expect(screen.getByRole("heading", { level: 1, name: "Weekly 1:1" })).toBeInTheDocument();
  expect(screen.getByText(/^Mon 28 Sept? · 13:51 · 12 min · 1:1$/)).toBeInTheDocument();
});

it("names who the 1:1 was with", async () => {
  const { props, rerender } = view();
  // no one yet: the date line offers to say who it was with
  await userEvent.click(screen.getByRole("button", { name: "Add who it was with" }));
  const input = screen.getByRole("combobox", { name: "Who the 1:1 was with" });
  expect(input).toHaveFocus();
  expect(input).toHaveValue("");
  const listed = document.getElementById(input.getAttribute("list") ?? "")?.querySelectorAll("option");
  expect(Array.from(listed ?? [], (option) => option.value)).toEqual(["Priya", "Sam"]);
  await userEvent.type(input, "Priya{Enter}");
  expect(props.onSetPerson).toHaveBeenCalledWith("Priya");
  expect(screen.queryByRole("combobox", { name: "Who the 1:1 was with" })).toBeNull();
  // Python said who it was with: the header names them, the name a quiet button
  rerender(<MeetingView {...props} detail={{ ...DETAIL, with: PRIYA }} />);
  const named = screen.getByRole("button", { name: "1:1 with Priya" });
  expect(named).toHaveTextContent(/^Priya$/);
  expect(named.closest("p")).toHaveTextContent(/^Mon 28 Sept? · 13:51 · 12 min · 1:1 with Priya$/);
  // Escape leaves it as it was
  await userEvent.click(named);
  const again = screen.getByRole("combobox", { name: "Who the 1:1 was with" });
  expect(again).toHaveValue("Priya");
  await userEvent.type(again, " Shah{Escape}");
  expect(props.onSetPerson).toHaveBeenCalledTimes(1);
  expect(screen.getByRole("button", { name: "1:1 with Priya" })).toHaveFocus();
  // an emptied name says it was with no one
  await userEvent.click(screen.getByRole("button", { name: "1:1 with Priya" }));
  await userEvent.clear(screen.getByRole("combobox", { name: "Who the 1:1 was with" }));
  await userEvent.keyboard("  {Enter}");
  expect(props.onSetPerson).toHaveBeenLastCalledWith("");
});

it("never lets the Enter that saves the name press the button the focus returns to", async () => {
  view();
  await userEvent.click(screen.getByRole("button", { name: "Add who it was with" }));
  const input = screen.getByRole("combobox", { name: "Who the 1:1 was with" });
  // a cancelled keydown sends no keypress, so the button never opens the input again
  expect(fireEvent.keyDown(input, { key: "Enter" })).toBe(false);
  expect(await screen.findByRole("button", { name: "Add who it was with" })).toHaveFocus();
});

it("keeps the name open when Evra refuses it", async () => {
  const onSetPerson = vi.fn(async (): Promise<WithRefusal | null> => "reserved");
  view({ onSetPerson });
  await userEvent.click(screen.getByRole("button", { name: "Add who it was with" }));
  await userEvent.type(screen.getByRole("combobox", { name: "Who the 1:1 was with" }), "you{Enter}");
  expect(await screen.findByText("Evra shows you as “You”. Pick another name.")).toBeInTheDocument();
  const input = screen.getByRole("combobox", { name: "Who the 1:1 was with" });
  expect(input).toHaveFocus();
  expect(input).toHaveValue("you");
  await userEvent.keyboard("{Escape}");
  expect(screen.queryByText("Evra shows you as “You”. Pick another name.")).toBeNull();
});

it("copies who the 1:1 was with", async () => {
  const writeText = mockClipboard(async () => {});
  view({ detail: { ...DETAIL, with: PRIYA } });
  fireEvent.click(screen.getByRole("button", { name: "Copy as Markdown" }));
  expect(await screen.findByRole("button", { name: "Copied" })).toBeInTheDocument();
  expect(writeText.mock.calls[0][0]).toMatch(/^# Weekly 1:1\nMon 28 Sept? · 13:51 · 12 min · 1:1 with Priya\n\n/);
});

it("never breaks a date or time in the title", () => {
  view({ detail: { ...DETAIL, meeting: { ...DETAIL.meeting, title: "Recording 2026-11-10 18:09" } } });
  const heading = screen.getByRole("heading", { level: 1, name: "Recording 2026-11-10 18:09" });
  expect(within(heading).getByText("2026-11-10")).toHaveClass("whitespace-nowrap");
  expect(within(heading).getByText("18:09")).toHaveClass("whitespace-nowrap");
});

it("shows where and how the note was written", () => {
  view();
  expect(screen.getByText("Written on this PC")).toBeInTheDocument();
  expect(screen.getByText("gemma4:12b")).toBeInTheDocument();
  expect(screen.getByText("2 points checked against the transcript")).toBeInTheDocument();
});

it("keeps the stamp and Copy away while a new note is written", () => {
  view({ noteStatus: { stage: "writing" } });
  expect(screen.queryByText("Written on this PC")).toBeNull();
  expect(screen.queryByRole("button", { name: "Copy as Markdown" })).toBeNull();
});

it("names the transcript tab without its line count", () => {
  view();
  const tab = screen.getByRole("tab", { name: "Transcript" });
  expect(tab).toHaveTextContent("2 lines");
});

it("copies the note as Markdown", async () => {
  const writeText = mockClipboard(async () => {});
  view();
  fireEvent.click(screen.getByRole("button", { name: "Copy as Markdown" }));
  expect(await screen.findByRole("button", { name: "Copied" })).toBeInTheDocument();
  const text = writeText.mock.calls[0][0] as string;
  expect(text).toMatch(/^# Weekly 1:1\nMon 28 Sept? · 13:51 · 12 min · 1:1\n\n## Summary\n/);
  expect(text).toContain("- Launch moves to October 14. (01:05)");
});

it("says when the note could not be copied", async () => {
  mockClipboard(async () => {
    throw new Error("denied");
  });
  view();
  fireEvent.click(screen.getByRole("button", { name: "Copy as Markdown" }));
  expect(await screen.findByRole("button", { name: "Couldn't copy" })).toBeInTheDocument();
});

it("arrow keys cycle note, transcript, ask and my notes", async () => {
  view();
  const note = screen.getByRole("tab", { name: "Note" });
  const transcript = screen.getByRole("tab", { name: "Transcript" });
  const ask = screen.getByRole("tab", { name: "Ask" });
  const notes = screen.getByRole("tab", { name: "My notes" });
  expect(note).toHaveAttribute("tabindex", "0");
  expect(transcript).toHaveAttribute("tabindex", "-1");
  expect(ask).toHaveAttribute("tabindex", "-1");
  expect(notes).toHaveAttribute("tabindex", "-1");
  note.focus();
  await userEvent.keyboard("{ArrowRight}");
  expect(transcript).toHaveAttribute("aria-selected", "true");
  expect(transcript).toHaveFocus();
  expect(note).toHaveAttribute("tabindex", "-1");
  await userEvent.keyboard("{ArrowRight}");
  expect(ask).toHaveAttribute("aria-selected", "true");
  expect(ask).toHaveFocus();
  expect(screen.getByRole("textbox", { name: "Ask about this meeting" })).toBeInTheDocument();
  await userEvent.keyboard("{ArrowRight}");
  expect(notes).toHaveAttribute("aria-selected", "true");
  expect(notes).toHaveFocus(); // the empty pad leaves the focus on the tab strip
  expect(screen.getByRole("textbox", { name: "Note line 1" })).toBeInTheDocument();
  await userEvent.keyboard("{ArrowRight}");
  expect(note).toHaveAttribute("aria-selected", "true");
  expect(note).toHaveFocus();
  await userEvent.keyboard("{ArrowLeft}");
  expect(notes).toHaveAttribute("aria-selected", "true");
  expect(notes).toHaveFocus();
  await userEvent.keyboard("{ArrowLeft}");
  expect(ask).toHaveAttribute("aria-selected", "true");
});

it("asks on the Ask tab, keeps Copy for the note, and jumps from an answer to its line", async () => {
  const answered: Question = {
    id: "q1",
    text: "What date does marketing want?",
    asked_at: 1,
    state: "answered",
    points: [{ text: "October 14.", citations: [{ utterance_id: "u1", start_ms: 65_000 }] }],
    excerpt: false,
    model: "gemma4:12b",
  };
  const { props } = view({ detail: { ...DETAIL, questions: [answered] } });
  await userEvent.click(screen.getByRole("tab", { name: "Ask" }));
  expect(props.onPrepareAsk).toHaveBeenCalledTimes(1);
  expect(screen.queryByRole("button", { name: "Copy as Markdown" })).toBeNull();
  expect(screen.getByRole("heading", { name: "What date does marketing want?" })).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "What did we decide?" }));
  expect(props.onAsk).toHaveBeenCalledWith("What did we decide?");
  await userEvent.click(screen.getByRole("button", { name: "Jump to 01:05 in the transcript" }));
  expect(screen.getByRole("tab", { name: "Transcript" })).toHaveAttribute("aria-selected", "true");
  expect(screen.getByText("Marketing wants October 14.").closest("li")).toHaveAttribute("data-highlighted", "true");
});
