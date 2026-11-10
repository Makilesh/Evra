import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";
import { MeetingView } from "@/components/MeetingView";
import { DETAIL } from "@/test/fakeApi";

function view(extra: Partial<Parameters<typeof MeetingView>[0]> = {}) {
  const props = {
    detail: DETAIL,
    isLive: false,
    noteStatus: undefined,
    hints: undefined,
    canWrite: true,
    onWrite: vi.fn(),
    onRename: vi.fn(async () => true),
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

it("opens a finished meeting on its note and a live one on its transcript", () => {
  view();
  expect(screen.getByRole("tab", { name: "Note" })).toHaveAttribute("aria-selected", "true");
  screen.getByText("Launch moves to October 14.");
});

it("opens a live meeting on the transcript, then the note once it is being written", () => {
  const { rerender, props } = view({ isLive: true });
  expect(screen.getByRole("tab", { name: "Transcript" })).toHaveAttribute("aria-selected", "true");
  rerender(<MeetingView {...props} isLive={false} noteStatus={{ stage: "writing" }} />);
  expect(screen.getByRole("tab", { name: "Note" })).toHaveAttribute("aria-selected", "true");
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
