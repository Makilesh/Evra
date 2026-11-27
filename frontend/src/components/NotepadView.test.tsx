import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { type ComponentProps, useState } from "react";
import { afterEach, expect, it, vi } from "vitest";
import type { NoteLine } from "@/bridge";
import { NotepadView } from "@/components/NotepadView";
import { DETAIL, MEETING } from "@/test/fakeApi";

afterEach(() => vi.restoreAllMocks());

type Props = ComponentProps<typeof NotepadView>;

const line = (id: string, text: string, captured_at: number | null = null): NoteLine => ({
  id,
  text,
  captured_at,
  pasted: false,
});

function props(extra: Partial<Props> = {}): Props {
  return {
    lines: [],
    meeting: MEETING,
    utterances: DETAIL.utterances,
    isLive: false,
    noted: false,
    onChange: vi.fn(),
    onJump: vi.fn(),
    ...extra,
  };
}

/** The pad with its lines kept in state, as useEvra keeps them; `seen` gets every change. */
function Pad({ initial = [], seen, ...extra }: Partial<Props> & { initial?: NoteLine[]; seen?: (lines: NoteLine[]) => void }) {
  const [lines, setLines] = useState(initial);
  const onChange = (next: NoteLine[]) => {
    setLines(next);
    seen?.(next);
  };
  return <NotepadView {...props(extra)} lines={lines} onChange={onChange} />;
}

function field(n: number): HTMLTextAreaElement {
  return screen.getByRole("textbox", { name: `Note line ${n}` });
}

function lastChange(seen: ReturnType<typeof vi.fn>): NoteLine[] {
  return seen.mock.lastCall?.[0] as NoteLine[];
}

it("opens an empty pad on one empty line, ready to type", () => {
  render(<Pad />);
  expect(field(1)).toHaveFocus();
  expect(field(1)).toHaveAttribute("placeholder", "Type a note. Each line is stamped with the time you wrote it.");
  expect(screen.getAllByRole("textbox")).toHaveLength(1);
});

it("leaves the focus where it is when the owner came along the tabs by keyboard", () => {
  render(<Pad focusOnOpen={false} />);
  expect(field(1)).not.toHaveFocus();
});

it("keeps the line being typed clear of the fade while live", () => {
  const typedLine = [line("a", "Budget approved")];
  const { rerender } = render(<NotepadView {...props()} isLive lines={typedLine} />);
  const pad = field(1).closest(".overflow-y-auto")!;
  // the pad fades its last 28px while live: scrolling to a line, or to the caret, stops 32px short
  expect(pad).toHaveClass("scroll-pb-8");
  rerender(<NotepadView {...props()} lines={typedLine} />);
  expect(pad).not.toHaveClass("scroll-pb-8");
});

it("keeps the focus ring every text field has", () => {
  render(<Pad initial={[line("a", "Budget approved")]} />);
  expect(field(1).className).not.toMatch(/outline-(hidden|none)/); // the global 2px rule-green ring
});

it("adds a line on Enter", async () => {
  const seen = vi.fn();
  render(<Pad seen={seen} />);
  await userEvent.type(field(1), "Budget approved{Enter}");
  expect(field(2)).toHaveFocus();
  expect(field(1)).toHaveValue("Budget approved"); // Enter starts a line, it never breaks one
  expect(lastChange(seen).map((l) => l.text)).toEqual(["Budget approved", ""]);
  await userEvent.keyboard("Ask Priya");
  expect(lastChange(seen).map((l) => l.text)).toEqual(["Budget approved", "Ask Priya"]);
});

it("removes an empty line on Backspace", async () => {
  const seen = vi.fn();
  render(<Pad seen={seen} initial={[line("a", "Budget approved"), line("b", "")]} />);
  field(2).focus();
  await userEvent.keyboard("{Backspace}");
  expect(screen.getAllByRole("textbox")).toHaveLength(1);
  expect(field(1)).toHaveFocus();
  expect(field(1)).toHaveValue("Budget approved"); // the line it went back to keeps its text
  expect(field(1).selectionStart).toBe("Budget approved".length);
  expect(lastChange(seen).map((l) => l.id)).toEqual(["a"]);
  await userEvent.keyboard("{Backspace}");
  expect(field(1)).toHaveValue("Budget approve"); // a line with text is edited, not removed
});

it("keeps the first typed time", async () => {
  const now = vi.spyOn(Date, "now").mockReturnValue(MEETING.started_at + 65_000);
  const seen = vi.fn();
  render(<Pad seen={seen} />);
  await userEvent.type(field(1), "  ");
  expect(lastChange(seen)[0].captured_at).toBeNull(); // spaces alone are not a note yet
  await userEvent.type(field(1), "Budget");
  expect(lastChange(seen)[0].captured_at).toBe(MEETING.started_at + 65_000);
  now.mockReturnValue(MEETING.started_at + 300_000);
  await userEvent.clear(field(1));
  await userEvent.type(field(1), "Budget approved");
  expect(lastChange(seen)[0].captured_at).toBe(MEETING.started_at + 65_000);
  expect(screen.getByRole("button", { name: "Jump to 01:05 in the transcript" })).toBeInTheDocument();
});

it("marks a long paste", async () => {
  const seen = vi.fn();
  render(<Pad seen={seen} />);
  field(1).focus();
  await userEvent.paste("x".repeat(500));
  expect(lastChange(seen)[0].pasted).toBe(false);
  await userEvent.paste("y".repeat(501));
  expect(lastChange(seen)[0]).toMatchObject({ pasted: true, text: "x".repeat(500) + "y".repeat(501) });
  await userEvent.type(field(1), "!");
  expect(lastChange(seen)[0].pasted).toBe(true); // it stays context
});

it("splits a paste longer than a line", async () => {
  const words = Array.from({ length: 1800 }, (_, i) => `word${i}`).join(" "); // 15,089 characters
  const seen = vi.fn();
  render(<Pad seen={seen} initial={[line("a", "Before"), line("b", "")]} />);
  field(2).focus();
  await userEvent.paste(words);
  const lines = lastChange(seen);
  expect(lines.length).toBe(5);
  expect(lines[0]).toEqual(line("a", "Before"));
  const pasted = lines.slice(1);
  expect(pasted.map((l) => l.text).join(" ")).toBe(words);
  expect(pasted.every((l) => l.text.length <= 4000 && l.pasted && l.captured_at !== null)).toBe(true);
  expect(new Set(lines.map((l) => l.id)).size).toBe(5);
  expect(field(5)).toHaveFocus();
});

it("adds no line past 2,000", async () => {
  const full = Array.from({ length: 2000 }, (_, i) => line(`l${i}`, `Line ${i}`));
  const seen = vi.fn();
  const { container } = render(<Pad seen={seen} initial={full} />);
  container.querySelectorAll("textarea")[1999].focus();
  await userEvent.keyboard("{Enter}");
  expect(container.querySelectorAll("textarea")).toHaveLength(2000);
  expect(seen).not.toHaveBeenCalled();
});

it("moves between lines with the arrow keys", async () => {
  render(<Pad initial={[line("a", "Budget approved"), line("b", "Ask")]} />);
  field(2).focus();
  field(2).setSelectionRange(3, 3); // after "Ask"
  await userEvent.keyboard("{ArrowUp}");
  expect(field(1)).toHaveFocus();
  expect(field(1).selectionStart).toBe(3); // the same place along the line, as far as it goes
  await userEvent.keyboard("{ArrowUp}"); // the first line has nothing above it
  expect(field(1)).toHaveFocus();
  await userEvent.keyboard("{ArrowDown}");
  expect(field(2)).toHaveFocus();
});

it("puts a line's typed time on the rule, which opens the transcript there", async () => {
  const onJump = vi.fn();
  render(
    <NotepadView
      {...props({ onJump })}
      lines={[line("a", "Proposal by Thursday", MEETING.started_at + 112_000), line("b", "Typed after the call", MEETING.started_at + 900_000)]}
    />,
  );
  await userEvent.click(screen.getByRole("button", { name: "Jump to 01:52 in the transcript" }));
  expect(onJump).toHaveBeenCalledWith(112_000);
  expect(screen.getAllByRole("button")).toHaveLength(1); // a line typed after the call has no time in it
});

it("shows the aligned lines after the note", () => {
  const linked: NoteLine = {
    ...line("a", "Launch slips to the 14th", MEETING.started_at + 70_000),
    aligned: [{ utterance_id: "u1", start_ms: 65_000 }],
  };
  const { rerender } = render(<NotepadView {...props()} lines={[linked]} />);
  expect(screen.queryByText("Marketing wants October 14.")).toBeNull();
  rerender(<NotepadView {...props()} lines={[linked]} noted />);
  const row = field(1).closest("li")!;
  expect(within(row).getByText("Marketing wants October 14.").tagName).toBe("Q");
  expect(row).toHaveTextContent("Them");
});

it("runs the last two transcript lines under the pad while live", () => {
  const third = { id: "u3", channel: 1, speaker: "Them", start_ms: 130_000, end_ms: 133_000, text: "Sounds good." };
  const { rerender } = render(<NotepadView {...props()} isLive utterances={[...DETAIL.utterances, third]} />);
  const strip = screen.getByRole("list", { name: "Transcript" });
  expect(within(strip).getAllByRole("listitem").map((li) => li.textContent)).toEqual([
    expect.stringContaining("I'll send the proposal by Thursday."),
    expect.stringContaining("Sounds good."),
  ]);
  expect(screen.getByRole("status")).toHaveTextContent("Listening…");
  rerender(<NotepadView {...props()} utterances={[...DETAIL.utterances, third]} />);
  expect(screen.queryByRole("list", { name: "Transcript" })).toBeNull();
  expect(screen.queryByRole("status")).toBeNull();
});
