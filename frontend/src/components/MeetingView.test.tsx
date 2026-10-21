import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
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
